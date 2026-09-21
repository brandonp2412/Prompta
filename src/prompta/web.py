"""Local web UI for Prompta's cached conversations and live replies."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import mimetypes
import socket
import subprocess
import threading
import time
from html import escape as html_escape
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlparse

from .attachment_store import AttachmentStore
from .cache import DEFAULT_CACHE_PATH, ChatCache
from .core import (
    DEFAULT_JOBS_PATH,
    DEFAULT_STATE_PATH,
    _daemon_is_running,
    _send_once_via_control,
    _send_reply_via_control,
    _stop_via_control,
    _sync_via_control,
)
from .image_previews import ImagePreviewStore
from .remote_control import remote_control as _remote_control
from .send_jobs import SendJobRegistry as SendJobRegistry
from .web_jobs import WebJobService
from .web_store import ReadOnlyChatStore as ReadOnlyChatStore

logger = logging.getLogger(__name__)
_STATIC_ROOT = Path(__file__).with_name("static")
_DAEMON_STARTUP_CHECKS = 10
_DAEMON_STARTUP_POLL_SECONDS = 0.1
_DAEMON_RESTART_GRACE_CHECKS = 120
_HOST_STATUS_TTL_SECONDS = 5.0
_HOST_CHECK_TIMEOUT_SECONDS = 3.0


def _git_short_head() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


_UI_HEAD = _git_short_head()




class PromptaUIServer(ThreadingHTTPServer):
    """Prompta UI with one local node and optional remote cache/control nodes."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        store: ReadOnlyChatStore,
        state_path: Path = DEFAULT_STATE_PATH,
        jobs_path: Path = DEFAULT_JOBS_PATH,
        *,
        control_host: str = "",
        server_name: str = "",
        extra_nodes: list[tuple[str, ReadOnlyChatStore, str]] | None = None,
    ) -> None:
        super().__init__(address, PromptaUIHandler)
        self.store = store
        self.state_path = state_path.expanduser()
        self.jobs_path = jobs_path.expanduser()
        self.control_host = control_host.strip()
        self._explicit_server_name = bool(server_name.strip())
        local_host = socket.gethostname().strip() or "localhost"
        self.host_name = (server_name.strip() or self.control_host or local_host).split(".", 1)[0]
        self._local_send_lock = threading.Lock()
        self._host_status_lock = threading.Lock()
        self._host_status_checked_at = 0.0
        self._host_status_online = not bool(self.control_host)
        self.image_previews = ImagePreviewStore(self.state_path.parent)
        self.attachments = AttachmentStore(self.state_path.parent, self.image_previews)
        self.job_service = WebJobService(
            self.jobs_path,
            self.state_path,
            self.host_name,
            start_scheduler=lambda: _start_local_scheduler_service(),
        )
        self.send_jobs = SendJobRegistry(
            self._send,
            recovery_path=self.state_path.parent / "ui-send-retries.json",
            on_success=self._bind_image_previews,
        )
        self.extra_nodes: dict[str, PromptaNodeTarget] = {}
        for node_name, node_store, node_control_host in extra_nodes or []:
            normalized = str(node_name).strip()
            if not normalized or normalized == self.host_name:
                continue
            self.extra_nodes[normalized] = PromptaNodeTarget(
                normalized,
                node_store,
                self.state_path,
                str(node_control_host),
                self.jobs_path,
            )

    @property
    def _image_previews(self) -> dict[str, dict[str, Any]]:
        return self.image_previews.records

    @property
    def _image_preview_path(self) -> Path:
        return self.image_previews.path

    @property
    def _image_preview_dir(self) -> Path:
        return self.image_previews.directory

    def _replace_staged_image_previews(
        self,
        client_id: str,
        message: str,
        images: list[dict[str, str]],
    ) -> None:
        self.image_previews.replace_staged(client_id, message, images)

    def _bind_image_previews(self, client_id: str, conversation_id: str, message: str) -> None:
        self.image_previews.bind(client_id, conversation_id, message)

    def _enrich_image_previews(self, chat: dict[str, Any], conversation_id: str) -> None:
        self.image_previews.enrich(chat, conversation_id)

    def image_preview(self, preview_id: str) -> tuple[bytes, str] | None:
        return self.image_previews.image_preview(preview_id)

    @property
    def display_name(self) -> str:
        return self.host_name.replace("-", " ").replace("_", " ").title()

    def host_online(self, *, force: bool = False) -> bool:
        if not self.control_host:
            return True
        now = time.monotonic()
        with self._host_status_lock:
            if not force and now - self._host_status_checked_at < _HOST_STATUS_TTL_SECONDS:
                return self._host_status_online
            try:
                completed = subprocess.run(
                    [
                        "ssh",
                        "-F",
                        str(Path.home() / ".ssh" / "config"),
                        "-o",
                        "BatchMode=yes",
                        "-o",
                        "ConnectTimeout=2",
                        "-o",
                        "ConnectionAttempts=1",
                        self.control_host,
                        "true",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=_HOST_CHECK_TIMEOUT_SECONDS,
                )
                online = completed.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                online = False
            self._host_status_checked_at = time.monotonic()
            self._host_status_online = online
            return online

    def iter_nodes(self):
        yield self
        yield from self.extra_nodes.values()

    def resolve_conversation(self, public_id: str):
        node_name, separator, actual_id = public_id.partition("::")
        if separator:
            target = self.extra_nodes.get(node_name)
            if target is None:
                raise KeyError(public_id)
            return target, actual_id
        return self, public_id

    @staticmethod
    def _public_chat(target, chat: dict[str, Any], local_target) -> dict[str, Any]:
        result = dict(chat)
        actual_id = str(result.get("id") or "")
        if target is not local_target:
            result["id"] = f"{target.host_name}::{actual_id}"
        result["node"] = target.host_name
        result["node_display"] = target.display_name
        return result

    def event_token(self) -> str:
        parts = []
        for target in self.iter_nodes():
            parts.append(
                f"{target.host_name}:{target.store.change_token()}:"
                f"send={target.send_jobs.revision}:online={int(target.host_online())}"
            )
        return "|".join(parts)

    def conversations(self, *, limit: int = 200, query: str = "") -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for target in self.iter_nodes():
            rows.extend(
                self._public_chat(target, chat, self)
                for chat in target.store.conversations(limit=limit, query=query)
            )
        rows.sort(
            key=lambda chat: (
                0 if str(chat.get("status") or "") == "active" else 1,
                -float(chat.get("updated_at") or 0.0),
            )
        )
        return rows[: max(1, min(limit, 500))]

    def conversation(self, public_id: str) -> dict[str, Any] | None:
        try:
            target, actual_id = self.resolve_conversation(public_id)
        except KeyError:
            return None
        chat = target.store.conversation(actual_id)
        if chat is None:
            return None
        result = self._public_chat(target, chat, self)
        if target is self:
            self._enrich_image_previews(result, actual_id)
        return result

    def stop_conversation(self, public_id: str) -> str:
        target, actual_id = self.resolve_conversation(public_id)
        if target.store.conversation(actual_id) is None:
            raise KeyError(public_id)
        return target._stop(actual_id)

    def probe_conversation(self, public_id: str) -> tuple[dict[str, Any], int]:
        target, actual_id = self.resolve_conversation(public_id)
        if target.store.conversation(actual_id) is None:
            raise KeyError(public_id)
        message_count = target._sync(actual_id)
        chat = self.conversation(public_id)
        if chat is None:
            raise KeyError(public_id)
        return chat, message_count

    def send_job(self, send_id: str) -> dict[str, Any] | None:
        for target in self.iter_nodes():
            job = target.send_jobs.get(send_id)
            if job is not None:
                result = dict(job)
                conversation_id = str(result.get("conversation_id") or "")
                if conversation_id and target is not self:
                    result["conversation_id"] = f"{target.host_name}::{conversation_id}"
                return result
        return None

    def logs(self, *, limit: int = 500) -> dict[str, Any]:
        return self.store.logs(limit=limit)

    def scheduled_jobs(self) -> dict[str, Any]:
        return self.job_service.scheduled_jobs()

    def _run_job_cli(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        return self.job_service.run_cli(action, payload)

    def save_attachments(
        self,
        raw_attachments: Any,
        *,
        client_id: str = "",
        message: str = "",
    ) -> list[str]:
        return self.attachments.save(
            raw_attachments,
            client_id=client_id,
            message=message,
        )

    def schedule_every(self, prompt: str, interval_minutes: float) -> dict[str, Any]:
        return self.job_service.schedule_every(prompt, interval_minutes)

    def schedule_at(self, prompt: str, run_at_epoch: float) -> dict[str, Any]:
        return self.job_service.schedule_at(prompt, run_at_epoch)

    def _stop(self, conversation_id: str) -> str:
        if self.control_host:
            return _remote_control(
                self.control_host,
                operation="stop",
                conversation_id=conversation_id,
            )
        if not _daemon_is_running(self.state_path):
            raise RuntimeError("Prompta scheduler is not running; cannot stop an active chat")
        return asyncio.run(_stop_via_control(self.state_path, conversation_id))

    def _sync(self, conversation_id: str) -> int:
        if self.control_host:
            return int(_remote_control(
                self.control_host,
                operation="sync",
                conversation_id=conversation_id,
            ))
        if not _daemon_is_running(self.state_path):
            raise RuntimeError("Prompta scheduler is not running; cannot inspect chat activity")
        return asyncio.run(_sync_via_control(self.state_path, conversation_id))

    def _send(
        self,
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str] | None = None,
    ) -> str:
        attachment_paths = list(attachments or [])
        if self.control_host:
            return _remote_control(
                self.control_host,
                operation=operation,
                message=message,
                conversation_id=conversation_id,
                attachments=attachment_paths,
            )
        with self._local_send_lock:
            scheduler_running = _wait_for_local_scheduler(self.state_path)
            if not scheduler_running and _start_local_scheduler_service():
                scheduler_running = _wait_for_local_scheduler(self.state_path)
            if not scheduler_running:
                raise RuntimeError(
                    "Prompta backend is unavailable after starting prompta.service"
                )
            if operation == "once":
                return asyncio.run(
                    _send_once_via_control(self.state_path, message, attachment_paths)
                )
            return asyncio.run(
                _send_reply_via_control(
                    self.state_path,
                    conversation_id,
                    message,
                    attachment_paths,
                )
            )


class PromptaNodeTarget:
    """Non-listening Prompta node exposed through the unified UI server."""

    def __init__(
        self,
        host_name: str,
        store: ReadOnlyChatStore,
        state_path: Path,
        control_host: str,
        jobs_path: Path,
    ) -> None:
        self.store = store
        self.state_path = state_path.expanduser()
        self.jobs_path = jobs_path.expanduser()
        self.control_host = control_host.strip()
        self.host_name = host_name.strip()
        self._local_send_lock = threading.Lock()
        self._host_status_lock = threading.Lock()
        self._host_status_checked_at = 0.0
        self._host_status_online = not bool(self.control_host)
        self.send_jobs = SendJobRegistry(
            self._send,
            recovery_path=self.state_path.parent / f"ui-send-retries-{self.host_name}.json",
        )

    @property
    def display_name(self) -> str:
        return self.host_name.replace("-", " ").replace("_", " ").title()

    host_online = PromptaUIServer.host_online
    _send = PromptaUIServer._send
    _stop = PromptaUIServer._stop
    _sync = PromptaUIServer._sync


class PromptaUIHandler(BaseHTTPRequestHandler):
    server_version = "PromptaUI/1"

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("%s - %s", self.address_string(), format % args)

    @property
    def store(self) -> ReadOnlyChatStore:
        return cast(PromptaUIServer, self.server).store

    @property
    def state_path(self) -> Path:
        return cast(PromptaUIServer, self.server).state_path

    def _json_body(self) -> dict[str, Any] | None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.casefold().startswith("application/json"):
            self._json({"error": "Expected application/json"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return None
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > 36 * 1024 * 1024:
            self._json({"error": "Invalid request size"}, HTTPStatus.BAD_REQUEST)
            return None
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json({"error": "Invalid JSON body"}, HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(payload, dict):
            self._json({"error": "Expected a JSON object"}, HTTPStatus.BAD_REQUEST)
            return None
        return payload

    def _send_payload_from_json_body(self) -> tuple[str, list[str], str] | None:
        payload = self._json_body()
        if payload is None:
            return None
        message = str(payload.get("message") or "")
        client_id = str(payload.get("client_id") or "").strip()
        try:
            attachments = cast(PromptaUIServer, self.server).save_attachments(
                payload.get("attachments"),
                client_id=client_id,
                message=message,
            )
        except (ValueError, OSError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return None
        if not message.strip() and not attachments:
            self._json({"error": "Message is empty"}, HTTPStatus.BAD_REQUEST)
            return None
        return message, attachments, client_id

    def _headers(
        self,
        status: HTTPStatus,
        content_type: str,
        content_length: int | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if content_length is not None:
            self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'; connect-src 'self'; "
            "font-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()

    def _write_response(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        try:
            self._headers(status, content_type, len(body))
            if getattr(self, "command", "GET") != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            logger.debug("Prompta UI client disconnected before response completed")

    def _json(
        self,
        payload: Any,
        status: HTTPStatus = HTTPStatus.OK,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self._write_response(status, content_type, body)

    def _manifest(self) -> None:
        server = cast(PromptaUIServer, self.server)
        app_name = f"Prompta · {server.display_name}"
        self._json(
            {
                "name": app_name,
                "short_name": app_name if server._explicit_server_name else f"Prompta {server.display_name}",
                "description": f"Prompta conversation UI for {server.display_name}",
                "id": "./",
                "start_url": "./",
                "scope": "./",
                "display": "standalone",
                "background_color": "#212121",
                "theme_color": "#212121",
                "icons": [
                    {
                        "src": "./icon.svg",
                        "sizes": "any",
                        "type": "image/svg+xml",
                        "purpose": "any maskable",
                    }
                ],
            },
            content_type="application/manifest+json; charset=utf-8",
        )

    def _index(self) -> None:
        server = cast(PromptaUIServer, self.server)
        try:
            page = (_STATIC_ROOT / "index.html").read_text()
            display_name = html_escape(server.display_name)
            page = page.replace("__PROMPTA_SERVER_NAME__", display_name)
            body = page.encode()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._write_response(HTTPStatus.OK, "text/html; charset=utf-8", body)




    def _static(self, relative_path: str, content_type: str | None = None) -> None:
        target = (_STATIC_ROOT / relative_path).resolve()
        try:
            target.relative_to(_STATIC_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            body = target.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime = content_type or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._write_response(
            HTTPStatus.OK,
            f"{mime}; charset=utf-8" if mime.startswith("text/") else mime,
            body,
        )

    def _event_headers(self) -> bool:
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            logger.debug("Prompta UI event client disconnected before response headers completed")
            return False
        return True

    def _events(self) -> None:
        server = cast(PromptaUIServer, self.server)
        if not self._event_headers():
            return

        last_token = ""
        last_heartbeat = 0.0
        try:
            self.wfile.write(b"retry: 1000\n\n")
            self.wfile.flush()
            while True:
                token = server.event_token()
                now = time.monotonic()
                if token != last_token:
                    payload = json.dumps(
                        {
                            "token": token,
                            "server": server.host_name,
                            "online": server.host_online(),
                            "head": _UI_HEAD,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    self.wfile.write(f"event: refresh\ndata: {payload}\n\n".encode())
                    self.wfile.flush()
                    last_token = token
                    last_heartbeat = now
                elif now - last_heartbeat >= 15.0:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_heartbeat = now
                time.sleep(0.2)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def do_HEAD(self) -> None:
        if urlparse(self.path).path == "/api/events":
            self._event_headers()
            return
        self.do_GET()


    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._index()
            return
        if path == "/app.css":
            self._static("app.css", "text/css")
            return
        if path == "/app.js":
            self._static("app.js", "text/javascript")
            return
        if path in {"/manifest.json", "/manifest.webmanifest"}:
            self._manifest()
            return
        if path == "/icon.svg":
            self._static("icon.svg", "image/svg+xml")
            return
        if path == "/sw.js":
            self._static("sw.js", "text/javascript")
            return
        if path == "/api/events":
            self._events()
            return
        if path == "/api/health":
            server = cast(PromptaUIServer, self.server)
            self._json({
                **self.store.stats(),
                "server": server.host_name,
                "online": True,
                "head": _UI_HEAD,
            })
            return
        if path == "/api/chats":
            query = parse_qs(parsed.query)
            search = query.get("q", [""])[0]
            try:
                limit = int(query.get("limit", ["200"])[0])
            except ValueError:
                limit = 200
            self._json({"chats": cast(PromptaUIServer, self.server).conversations(limit=limit, query=search)})
            return
        if path == "/api/logs":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["500"])[0])
            except ValueError:
                limit = 500
            self._json(cast(PromptaUIServer, self.server).logs(limit=limit))
            return
        if path == "/api/jobs":
            self._json(cast(PromptaUIServer, self.server).scheduled_jobs())
            return
        preview_prefix = "/api/attachment-previews/"
        if path.startswith(preview_prefix):
            preview_id = unquote(path[len(preview_prefix) :]).strip("/")
            preview = cast(PromptaUIServer, self.server).image_preview(preview_id)
            if preview is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body, media_type = preview
            self._write_response(HTTPStatus.OK, media_type, body)
            return
        send_prefix = "/api/sends/"
        if path.startswith(send_prefix):
            send_id = unquote(path[len(send_prefix) :]).strip("/")
            job = cast(PromptaUIServer, self.server).send_job(send_id)
            if job is None:
                self._json({"error": "Send not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(job)
            return
        prefix = "/api/chats/"
        if path.startswith(prefix):
            conversation_id = unquote(path[len(prefix) :])
            chat = cast(PromptaUIServer, self.server).conversation(conversation_id)
            if chat is None:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(chat)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/jobs":
            payload = self._json_body()
            if payload is None:
                return
            action = str(payload.get("action") or "").strip().lower()
            try:
                result = cast(PromptaUIServer, self.server)._run_job_cli(action, payload)
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                logger.exception("Prompta UI jobs command failed")
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._json(result)
            return

        if path == "/api/schedule":
            payload = self._json_body()
            if payload is None:
                return
            prompt = str(payload.get("prompt") or "").strip()
            try:
                interval_minutes = float(str(payload.get("interval_minutes") or ""))
            except (TypeError, ValueError):
                interval_minutes = 0.0
            if not prompt:
                self._json({"error": "Schedule prompt is empty"}, HTTPStatus.BAD_REQUEST)
                return
            if not math.isfinite(interval_minutes) or interval_minutes <= 0:
                self._json({"error": "Schedule interval must be a finite value greater than zero"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                result = cast(PromptaUIServer, self.server).schedule_every(
                    prompt,
                    interval_minutes,
                )
            except Exception as exc:
                logger.exception("Prompta UI scheduling failed")
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._json({"ok": True, **result}, HTTPStatus.CREATED)
            return

        if path == "/api/schedule-at":
            payload = self._json_body()
            if payload is None:
                return
            prompt = str(payload.get("prompt") or "").strip()
            try:
                run_at_epoch = float(str(payload.get("run_at_epoch") or ""))
            except (TypeError, ValueError):
                run_at_epoch = 0.0
            if not prompt:
                self._json({"error": "Schedule prompt is empty"}, HTTPStatus.BAD_REQUEST)
                return
            if not math.isfinite(run_at_epoch) or run_at_epoch <= time.time():
                self._json({"error": "Schedule time must be a finite timestamp in the future"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                result = cast(PromptaUIServer, self.server).schedule_at(prompt, run_at_epoch)
            except Exception as exc:
                logger.exception("Prompta UI one-time scheduling failed")
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._json({"ok": True, **result}, HTTPStatus.CREATED)
            return

        if path == "/api/chats":
            send_payload = self._send_payload_from_json_body()
            if send_payload is None:
                return
            message, attachments, client_id = send_payload
            job = cast(PromptaUIServer, self.server).send_jobs.submit(
                operation="once",
                message=message,
                attachments=attachments,
                client_id=client_id,
            )
            self._json({"ok": True, **job}, HTTPStatus.ACCEPTED)
            return

        prefix = "/api/chats/"
        probe_suffix = "/probe"
        if path.startswith(prefix) and path.endswith(probe_suffix):
            conversation_id = unquote(path[len(prefix) : -len(probe_suffix)]).strip("/")
            if not conversation_id:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                chat, message_count = cast(PromptaUIServer, self.server).probe_conversation(conversation_id)
            except KeyError:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            except Exception as exc:
                logger.exception("Prompta UI activity probe failed conversation=%s", conversation_id)
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._json({"ok": True, "chat": chat, "message_count": message_count})
            return

        stop_suffix = "/stop"
        if path.startswith(prefix) and path.endswith(stop_suffix):
            conversation_id = unquote(path[len(prefix) : -len(stop_suffix)]).strip("/")
            if not conversation_id:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                stopped_id = cast(PromptaUIServer, self.server).stop_conversation(conversation_id)
            except KeyError:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            except Exception as exc:
                logger.exception("Prompta UI stop failed conversation=%s", conversation_id)
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._json({"ok": True, "conversation_id": conversation_id, "stopped_id": stopped_id})
            return

        suffix = "/messages"
        if not (path.startswith(prefix) and path.endswith(suffix)):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        conversation_id = unquote(path[len(prefix) : -len(suffix)]).strip("/")
        server = cast(PromptaUIServer, self.server)
        if not conversation_id or server.store.conversation(conversation_id) is None:
            self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
            return

        send_payload = self._send_payload_from_json_body()
        if send_payload is None:
            return
        message, attachments, client_id = send_payload

        job = server.send_jobs.submit(
            operation="reply",
            conversation_id=conversation_id,
            message=message,
            attachments=attachments,
            client_id=client_id,
        )
        job["conversation_id"] = conversation_id
        self._json({"ok": True, **job}, HTTPStatus.ACCEPTED)


def _start_local_scheduler_service() -> bool:
    """Ask systemd to own the local Firefox session when the service is available."""

    try:
        started = subprocess.run(
            ["systemctl", "--user", "start", "prompta.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("Could not start Prompta scheduler service", exc_info=True)
        return False
    if started.returncode != 0:
        detail = (started.stderr or started.stdout or "").strip()
        logger.info(
            "Prompta scheduler service could not be started%s",
            f": {detail[-500:]}" if detail else "",
        )
        return False
    return True


def _wait_for_local_scheduler(state_path: Path) -> bool:
    """Allow a systemd-style scheduler restart to reclaim its daemon lock."""

    for attempt in range(_DAEMON_RESTART_GRACE_CHECKS):
        if _daemon_is_running(state_path):
            return True
        if attempt + 1 < _DAEMON_RESTART_GRACE_CHECKS:
            time.sleep(_DAEMON_STARTUP_POLL_SECONDS)
    return False


def _reconcile_orphaned_local_chats(
    cache_path: Path,
    state_path: Path,
) -> int:
    for attempt in range(_DAEMON_STARTUP_CHECKS):
        if _daemon_is_running(state_path):
            return 0
        if attempt + 1 < _DAEMON_STARTUP_CHECKS:
            time.sleep(_DAEMON_STARTUP_POLL_SECONDS)
    cache = ChatCache(cache_path)
    try:
        return cache.mark_orphaned_active()
    finally:
        cache.close()


def serve(
    cache_path: Path,
    log_path: Path | None,
    host: str,
    port: int,
    state_path: Path = DEFAULT_STATE_PATH,
    jobs_path: Path = DEFAULT_JOBS_PATH,
    preserve_active: bool = False,
) -> None:
    orphaned = (
        0
        if preserve_active
        else _reconcile_orphaned_local_chats(cache_path, state_path)
    )
    if orphaned:
        logger.info(
            "Prompta UI marked %d orphaned local conversation(s) interrupted",
            orphaned,
        )
    store = ReadOnlyChatStore(cache_path, log_path)
    server = PromptaUIServer(
        (host, port),
        store,
        state_path,
        jobs_path,
    )
    logger.info("Prompta UI listening on http://%s:%d", host, port)
    logger.info("Reading cache %s in SQLite query-only mode", cache_path.expanduser())
    logger.info("Sending replies through the local prompta.service control socket")
    logger.info("Reading logs from %s", store.log_path)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Prompta conversation UI")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    parser.add_argument("--logs", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--preserve-active",
        action="store_true",
        help="Leave scheduler-owned active cache rows untouched during UI-only restarts",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    serve(
        args.cache,
        args.logs,
        args.host,
        max(1, min(args.port, 65535)),
        args.state,
        args.jobs_file,
        args.preserve_active,
    )


if __name__ == "__main__":
    main()
