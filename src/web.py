"""Local web UI for Prompta's cached conversations and live replies."""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import math
import mimetypes
import os
import socket
import subprocess
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
    _stop_via_control,
    _sync_via_control,
)
from .delivery_queue import DeliveryQueueStore
from .image_previews import ImagePreviewStore
from .pinned_chats import PinnedChatStore
from .read_state import ConversationReadState
from .scheduler_runtime import SchedulerRuntime
from .send_jobs import SendJobRegistry as SendJobRegistry
from .service_health import ServiceHealthStore, browser_page_count, notify_watchdog
from .web_jobs import WebJobService
from .web_store import ReadOnlyChatStore as ReadOnlyChatStore

logger = logging.getLogger(__name__)
_STATIC_ROOT = Path(__file__).with_name("static")
_DAEMON_STARTUP_CHECKS = 10
_DAEMON_STARTUP_POLL_SECONDS = 0.1
_DAEMON_RESTART_GRACE_CHECKS = 120
_EVENT_HEARTBEAT_SECONDS = 5.0


def _git_short_head() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


def _git_changelog() -> list[dict[str, str]]:
    try:
        completed = subprocess.run(
            ["git", "log", "--format=%h%x09%s", "HEAD"],
            cwd=Path(__file__).resolve().parents[1],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if completed.returncode != 0:
        return []
    entries = []
    for line in completed.stdout.splitlines():
        short_hash, separator, title = line.partition("	")
        short_hash = short_hash.strip().lower()
        title = title.strip()
        if separator and short_hash and title:
            entries.append({"hash": short_hash, "title": title})
    return entries


_UI_HEAD = _git_short_head()
_UI_CHANGELOG = _git_changelog()


class PromptaUIServer(ThreadingHTTPServer):
    """Prompta UI and local backend control surface."""

    daemon_threads = True

    _UNUSED_UI_MESSAGE_FIELDS = frozenset({"tool_calls", "source_event_count", "version_count"})

    @classmethod
    def _compact_conversation_detail(cls, chat: dict[str, Any]) -> dict[str, Any]:
        result = {key: value for key, value in chat.items() if key != "state_events"}
        messages = result.get("messages")
        if isinstance(messages, list):
            result["messages"] = [
                {
                    key: value
                    for key, value in message.items()
                    if key not in cls._UNUSED_UI_MESSAGE_FIELDS
                }
                if isinstance(message, dict)
                else message
                for message in messages
            ]
        return result

    def __init__(
        self,
        address: tuple[str, int],
        store: ReadOnlyChatStore,
        state_path: Path = DEFAULT_STATE_PATH,
        jobs_path: Path = DEFAULT_JOBS_PATH,
    ) -> None:
        super().__init__(address, PromptaUIHandler)
        self.store = store
        self.state_path = state_path.expanduser()
        self.jobs_path = jobs_path.expanduser()
        local_host = socket.gethostname().strip() or "localhost"
        self.host_name = local_host.split(".", 1)[0]
        self.image_previews = ImagePreviewStore(self.state_path.parent)
        self.attachments = AttachmentStore(self.state_path.parent, self.image_previews)
        self.pinned_chats = PinnedChatStore(self.state_path.parent)
        self.read_state = ConversationReadState(self.state_path.parent)
        self.scheduler_runtime = SchedulerRuntime(self.state_path, self.jobs_path)
        self.service_health_store = ServiceHealthStore(self.state_path)
        self.delivery_queue = DeliveryQueueStore(self.state_path.parent / "ui-send-jobs.sqlite3")
        self._last_health_beat = 0.0
        self.job_service = WebJobService(
            self.jobs_path,
            self.state_path,
            self.host_name,
            start_scheduler=lambda: _start_local_scheduler_service(),
        )
        self.send_jobs = SendJobRegistry(
            None,
            queue_path=self.state_path.parent / "ui-send-jobs.sqlite3",
            consume=False,
        )
        self.service_health_store.beat("ui")

    def service_actions(self) -> None:
        super().service_actions()
        now = time.time()
        if now - self._last_health_beat < 5.0:
            return
        self.service_health_store.beat("ui", now=now)
        notify_watchdog()
        self._last_health_beat = now

    def liveness_status(self) -> dict[str, Any]:
        now = time.time()
        debugger_address = os.environ.get(
            "PROMPTA_CHROME_DEBUGGER_ADDRESS",
            "127.0.0.1:9222",
        )
        browser_reachable, page_count = browser_page_count(debugger_address)
        if browser_reachable:
            self.service_health_store.beat("browser", now=now)

        services = self.service_health_store.snapshot(now=now)
        queue = self.delivery_queue.health_metrics(now=now)
        scheduler = services["scheduler"]
        delivery = services["delivery_worker"]
        conversation = services["conversation_worker"]
        browser = services["browser"]
        ui = services["ui"]
        return {
            "services": services,
            "ui": {
                "heartbeat_at": ui["heartbeat_at"],
                "heartbeat_age_seconds": ui["heartbeat_age_seconds"],
                "stale": ui["stale"],
            },
            "scheduler": {
                "last_tick_at": scheduler["heartbeat_at"],
                "last_tick_age_seconds": scheduler["heartbeat_age_seconds"],
                "stale": scheduler["stale"],
            },
            "delivery_worker": {
                "heartbeat_at": delivery["heartbeat_at"],
                "heartbeat_age_seconds": delivery["heartbeat_age_seconds"],
                "stale": delivery["stale"],
                "current_lease_age_seconds": queue["current_lease_age_seconds"],
                "current_lease_send_id": queue["current_lease_send_id"],
                "oldest_ready_delivery_age_seconds": queue["oldest_ready_age_seconds"],
                "last_successful_delivery_at": queue["last_successful_delivery_at"],
                "last_successful_delivery_send_id": queue["last_successful_delivery_send_id"],
                "last_successful_delivery_conversation_id": queue[
                    "last_successful_delivery_conversation_id"
                ],
            },
            "conversation_worker": {
                "heartbeat_at": conversation["heartbeat_at"],
                "heartbeat_age_seconds": conversation["heartbeat_age_seconds"],
                "stale": conversation["stale"],
                "current_poll_age_seconds": (
                    conversation["activity_age_seconds"]
                    if conversation["activity"] == "poll"
                    else None
                ),
            },
            "browser": {
                "reachable": browser_reachable,
                "page_count": page_count,
                "heartbeat_at": browser["heartbeat_at"],
                "heartbeat_age_seconds": browser["heartbeat_age_seconds"],
                "stale": browser["stale"],
            },
        }

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
        return True

    def unattended_mode(self) -> dict[str, Any]:
        enabled = self.scheduler_runtime.unattended_mode()
        return {
            "unattended": enabled,
            "chat_polling": not enabled,
            "send_gap_seconds": self.scheduler_runtime.send_gap_seconds(),
        }

    def set_unattended_mode(self, enabled: bool) -> dict[str, Any]:
        self.scheduler_runtime.set_unattended_mode(enabled)
        return self.unattended_mode()

    def event_token(self) -> str:
        mode = int(self.scheduler_runtime.unattended_mode())
        return (
            f"{self.store.change_token()}:"
            f"send={self.send_jobs.revision}:online={int(self.host_online())}:unattended={mode}"
        )

    @staticmethod
    def _send_conversation_id(job: dict[str, Any]) -> str:
        conversation_id = str(job.get("conversation_id") or "").strip()
        if conversation_id:
            return conversation_id
        client_id = str(job.get("client_id") or "").strip()
        send_id = str(job.get("send_id") or "").strip()
        return f"pending-new-{client_id or send_id}" if client_id or send_id else ""

    @classmethod
    def _send_conversation_summary(cls, job: dict[str, Any]) -> dict[str, Any]:
        conversation_id = cls._send_conversation_id(job)
        message = str(job.get("message") or "")
        created_at = float(job.get("created_at") or 0.0)
        updated_at = float(job.get("updated_at") or created_at)
        return {
            "id": conversation_id,
            "job_name": "new chat",
            "prompt": message,
            "url": "",
            "title": message[:72] or "New chat",
            "status": "pending",
            "created_at": created_at,
            "updated_at": updated_at,
            "completed_at": None,
            "last_message_at": created_at,
            "preview": message,
            "message_count": 1,
            "_pending_send": True,
            "_send_id": str(job.get("send_id") or ""),
            "_client_id": str(job.get("client_id") or ""),
        }

    @staticmethod
    def _retry_delay_label(job: dict[str, Any]) -> str:
        retry_at = float(job.get("retry_at") or 0.0)
        retry_after = float(job.get("retry_after_seconds") or 0.0)
        remaining = max(0.0, retry_at - time.time()) if retry_at > 0 else max(0.0, retry_after)
        if remaining <= 0:
            return "retrying now"
        if remaining < 60:
            return "retry in <1m"
        minutes = math.ceil(remaining / 60)
        if minutes < 60:
            return f"retry in {minutes}m"
        return f"retry in {math.ceil(minutes / 60)}h"

    @staticmethod
    def _queue_eta_label(job: dict[str, Any]) -> str:
        queue_eta_at = float(job.get("queue_eta_at") or 0.0)
        remaining = max(0.0, queue_eta_at - time.time())
        if remaining <= 0:
            return ""
        minutes = max(1, math.ceil(remaining / 60))
        if minutes < 60:
            return f"ETA ~{minutes}m"
        hours, remaining_minutes = divmod(minutes, 60)
        if hours < 24:
            return f"ETA ~{hours}h {remaining_minutes}m" if remaining_minutes else f"ETA ~{hours}h"
        days, remaining_hours = divmod(hours, 24)
        return f"ETA ~{days}d {remaining_hours}h" if remaining_hours else f"ETA ~{days}d"

    @classmethod
    def _send_conversation_detail(cls, job: dict[str, Any]) -> dict[str, Any]:
        summary = cls._send_conversation_summary(job)
        message = str(job.get("message") or "")
        created_at = float(job.get("created_at") or 0.0)
        updated_at = float(job.get("updated_at") or created_at)
        summary["messages"] = [
            {
                "message_key": f"pending-send-{str(job.get('send_id') or job.get('client_id') or 'new')}",
                "ordinal": 0,
                "role": "user",
                "content": message,
                "status": "complete",
                "created_at": created_at,
                "updated_at": updated_at,
                "parts": [],
                "tool_calls": [],
                "source_event_count": 0,
                "version_count": 0,
            }
        ]
        send_status = str(job.get("status") or "")
        if send_status in {"queued", "running", "retrying", "rate_limited"}:
            queue_position = int(job.get("queue_position") or 0)
            if send_status == "queued":
                activity_label = f"queued · #{queue_position}" if queue_position > 0 else "queued"
                queue_eta = cls._queue_eta_label(job)
                if queue_eta:
                    activity_label = f"{activity_label} · {queue_eta}"
            elif send_status == "retrying":
                activity_label = "retrying"
            elif send_status == "rate_limited":
                activity_label = f"rate limited · {cls._retry_delay_label(job)}"
            else:
                activity_label = "waiting"
            summary["messages"].append(
                {
                    "message_key": (
                        f"pending-activity-{str(job.get('send_id') or job.get('client_id') or 'new')}"
                    ),
                    "ordinal": 1,
                    "role": "assistant",
                    "content": "",
                    "status": "pending",
                    "created_at": updated_at,
                    "updated_at": updated_at,
                    "pending_activity": True,
                    "pending_activity_label": activity_label,
                    "parts": [],
                    "tool_calls": [],
                    "source_event_count": 0,
                    "version_count": 0,
                }
            )
        summary["state_events"] = []
        return summary

    def conversations(
        self,
        *,
        limit: int = 200,
        query: str = "",
        include_ids: list[str] | tuple[str, ...] = (),
    ) -> list[dict[str, Any]]:
        bounded_limit = max(1, min(limit, 500))
        included_ids = list(
            dict.fromkeys(str(value).strip() for value in include_ids if str(value).strip())
        )[:100]
        rows = [
            dict(chat)
            for chat in self.store.conversations(
                limit=bounded_limit,
                query=query,
                include_ids=included_ids,
            )
        ]
        known_ids = {str(chat.get("id") or "") for chat in rows}
        needle = query.strip().casefold()

        for job in self.send_jobs.list_conversation_receipts():
            summary = self._send_conversation_summary(job)
            if not summary["id"] or summary["id"] in known_ids:
                continue
            if needle and not any(
                needle in str(summary.get(field) or "").casefold()
                for field in ("title", "job_name", "prompt", "preview")
            ):
                continue
            rows.append(summary)
            known_ids.add(summary["id"])

        rows = self.read_state.decorate(rows)
        pinned_ids = set(included_ids)
        rows.sort(
            key=lambda chat: (
                0 if str(chat.get("id") or "") in pinned_ids else 1,
                0 if bool(chat.get("_pending_send")) else 1,
                -float(chat.get("created_at") or 0.0),
                str(chat.get("id") or ""),
            )
        )
        unpinned_ids = [
            str(chat.get("id") or "")
            for chat in rows
            if str(chat.get("id") or "") and str(chat.get("id") or "") not in pinned_ids
        ]
        selected_ids = set(included_ids) | set(unpinned_ids[:bounded_limit])
        return [chat for chat in rows if str(chat.get("id") or "") in selected_ids]

    def conversation_page(
        self,
        *,
        limit: int = 200,
        query: str = "",
        include_ids: list[str] | tuple[str, ...] = (),
    ) -> dict[str, Any]:
        bounded_limit = max(1, min(limit, 500))
        probe_limit = min(bounded_limit + 1, 500)
        rows = self.conversations(
            limit=probe_limit,
            query=query,
            include_ids=include_ids,
        )
        pinned_ids = (
            {str(value).strip() for value in include_ids if str(value).strip()}
            if not query.strip()
            else set()
        )
        visible: list[dict[str, Any]] = []
        ordinary_count = 0
        has_more = False

        for chat in rows:
            chat_id = str(chat.get("id") or "")
            if chat_id in pinned_ids:
                visible.append(chat)
                continue
            if ordinary_count >= bounded_limit:
                has_more = True
                continue
            visible.append(chat)
            ordinary_count += 1

        return {"chats": visible, "has_more": has_more}

    def conversation(self, conversation_id: str) -> dict[str, Any] | None:
        chat = self.store.conversation(conversation_id, include_state_events=False)
        if chat is None:
            for job in self.send_jobs.list_conversation_receipts():
                if self._send_conversation_id(job) == conversation_id:
                    return self._compact_conversation_detail(self._send_conversation_detail(job))
            return None
        result = self._compact_conversation_detail(chat)
        self._enrich_image_previews(result, conversation_id)
        return result

    def stop_conversation(self, conversation_id: str) -> str:
        if self.store.conversation(conversation_id, include_state_events=False) is None:
            raise KeyError(conversation_id)
        return self._stop(conversation_id)

    def probe_conversation(self, conversation_id: str) -> tuple[dict[str, Any], int, bool]:
        if self.scheduler_runtime.unattended_mode():
            raise RuntimeError("Machine Gun Mode disables ChatGPT result reads")
        if self.store.conversation(conversation_id, include_state_events=False) is None:
            raise KeyError(conversation_id)
        verified = True
        try:
            message_count = self._sync(conversation_id)
        except RuntimeError as exc:
            if str(exc) != "ChatGPT conversation did not expose any messages":
                raise
            verified = False
            message_count = 0
        chat = self.conversation(conversation_id)
        if chat is None:
            raise KeyError(conversation_id)
        if not verified:
            messages = chat.get("messages")
            message_count = len(messages) if isinstance(messages, list) else 0
        return chat, message_count, verified

    def send_job(self, send_id: str) -> dict[str, Any] | None:
        job = self.send_jobs.get(send_id)
        return dict(job) if job is not None else None

    def pending_sends(self) -> list[dict[str, Any]]:
        return self.send_jobs.list_pending()

    def admission_status(self) -> dict[str, Any]:
        return self.scheduler_runtime.account_admission_status()

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
        if not _daemon_is_running(self.state_path):
            raise RuntimeError("Prompta browser backend is not running; cannot stop an active chat")
        return asyncio.run(_stop_via_control(self.state_path, conversation_id))

    def _sync(self, conversation_id: str) -> int:
        if not _daemon_is_running(self.state_path):
            raise RuntimeError(
                "Prompta browser backend is not running; cannot inspect chat activity"
            )
        return asyncio.run(_sync_via_control(self.state_path, conversation_id))


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
            "style-src 'self' 'unsafe-inline'; script-src 'self'; connect-src 'self'; "
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
                "short_name": f"Prompta {server.display_name}",
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
        relative = Path(relative_path)
        if relative.is_absolute() or ".." in relative.parts:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        target = _STATIC_ROOT / relative
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

    def _service_worker(self) -> None:
        try:
            script = (_STATIC_ROOT / "sw.js").read_text()
            body = script.replace("__PROMPTA_UI_HEAD__", _UI_HEAD or "dev").encode()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._write_response(HTTPStatus.OK, "text/javascript; charset=utf-8", body)

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
                elif now - last_heartbeat >= _EVENT_HEARTBEAT_SECONDS:
                    payload = json.dumps(
                        {
                            "server": server.host_name,
                            "online": server.host_online(),
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    self.wfile.write(f"event: heartbeat\ndata: {payload}\n\n".encode())
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
            self._service_worker()
            return
        if path == "/api/events":
            self._events()
            return
        if path == "/api/health":
            server = cast(PromptaUIServer, self.server)
            self._json(
                {
                    **self.store.stats(),
                    "server": server.host_name,
                    "online": server.host_online(force=True),
                    "head": _UI_HEAD,
                    "admission": server.admission_status(),
                    "liveness": server.liveness_status(),
                    **server.unattended_mode(),
                }
            )
            return
        if path == "/api/mode":
            self._json(cast(PromptaUIServer, self.server).unattended_mode())
            return
        if path == "/api/changelog":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["100"])[0])
            except ValueError:
                limit = 100
            bounded_limit = max(1, min(limit, 5_000))
            self._json(
                {
                    "changes": _UI_CHANGELOG[:bounded_limit],
                    "has_more": len(_UI_CHANGELOG) > bounded_limit,
                    "total": len(_UI_CHANGELOG),
                }
            )
            return
        if path == "/api/pins":
            self._json(cast(PromptaUIServer, self.server).pinned_chats.snapshot())
            return
        if path == "/api/chats":
            query = parse_qs(parsed.query)
            search = query.get("q", [""])[0]
            include_ids = query.get("include", [])
            try:
                limit = int(query.get("limit", ["200"])[0])
            except ValueError:
                limit = 200
            self._json(
                cast(PromptaUIServer, self.server).conversation_page(
                    limit=limit,
                    query=search,
                    include_ids=include_ids,
                )
            )
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
        if path == "/api/sends":
            server = cast(PromptaUIServer, self.server)
            self._json(
                {
                    "jobs": server.pending_sends(),
                    "admission": server.admission_status(),
                }
            )
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

    def do_DELETE(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        prefix = "/api/sends/"
        if not path.startswith(prefix):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        send_id = unquote(path[len(prefix) :]).strip("/")
        if not send_id:
            self._json({"error": "Send not found"}, HTTPStatus.NOT_FOUND)
            return
        cancelled = cast(PromptaUIServer, self.server).send_jobs.cancel(send_id)
        if not cancelled:
            self._json({"error": "Send is no longer pending"}, HTTPStatus.NOT_FOUND)
            return
        self._json({"ok": True, "send_id": send_id})

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/mode":
            payload = self._json_body()
            if payload is None:
                return
            unattended = payload.get("unattended")
            if not isinstance(unattended, bool):
                self._json({"error": "Expected unattended to be a boolean"}, HTTPStatus.BAD_REQUEST)
                return
            self._json(cast(PromptaUIServer, self.server).set_unattended_mode(unattended))
            return

        if path == "/api/pins/seed":
            payload = self._json_body()
            if payload is None:
                return
            ids = payload.get("ids")
            if not isinstance(ids, list):
                self._json({"error": "Expected ids to be a list"}, HTTPStatus.BAD_REQUEST)
                return
            self._json(cast(PromptaUIServer, self.server).pinned_chats.seed(ids))
            return

        if path == "/api/pins/promote":
            payload = self._json_body()
            if payload is None:
                return
            previous_id = str(payload.get("from") or "").strip()
            next_id = str(payload.get("to") or "").strip()
            try:
                result = cast(PromptaUIServer, self.server).pinned_chats.promote(
                    previous_id, next_id
                )
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._json(result)
            return

        if path == "/api/pins":
            payload = self._json_body()
            if payload is None:
                return
            chat_id = str(payload.get("id") or "").strip()
            pinned = payload.get("pinned")
            if not isinstance(pinned, bool):
                self._json({"error": "Expected pinned to be a boolean"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                result = cast(PromptaUIServer, self.server).pinned_chats.set_pinned(chat_id, pinned)
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._json(result)
            return

        if path == "/api/chats/read-all":
            self._json(cast(PromptaUIServer, self.server).read_state.mark_all_read())
            return

        read_prefix = "/api/chats/"
        read_suffix = "/read"
        if path.startswith(read_prefix) and path.endswith(read_suffix):
            conversation_id = unquote(path[len(read_prefix) : -len(read_suffix)]).strip("/")
            try:
                result = cast(PromptaUIServer, self.server).read_state.mark_read(conversation_id)
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._json(result)
            return

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
                self._json(
                    {"error": "Schedule interval must be a finite value greater than zero"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            try:
                result = cast(PromptaUIServer, self.server).schedule_every(
                    prompt,
                    interval_minutes,
                )
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                logger.exception("Prompta UI scheduling failed")
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            status = HTTPStatus.CREATED if result.get("created") is not False else HTTPStatus.OK
            self._json({"ok": True, **result}, status)
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
                self._json(
                    {"error": "Schedule time must be a finite timestamp in the future"},
                    HTTPStatus.BAD_REQUEST,
                )
                return
            try:
                result = cast(PromptaUIServer, self.server).schedule_at(prompt, run_at_epoch)
            except Exception as exc:
                logger.exception("Prompta UI one-time scheduling failed")
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._json({"ok": True, **result}, HTTPStatus.CREATED)
            return

        send_prefix = "/api/sends/"
        bump_suffix = "/bump"
        if path.startswith(send_prefix) and path.endswith(bump_suffix):
            send_id = unquote(path[len(send_prefix) : -len(bump_suffix)]).strip("/")
            if not send_id:
                self._json({"error": "Send not found"}, HTTPStatus.NOT_FOUND)
                return

            server = cast(PromptaUIServer, self.server)
            job = server.send_jobs.bump_to_front(send_id)
            if job is None:
                current = server.send_jobs.get(send_id)
                status = HTTPStatus.NOT_FOUND if current is None else HTTPStatus.CONFLICT
                error = "Send not found" if current is None else "Send is no longer pending"
                self._json({"error": error}, status)
                return

            self._json({"ok": True, **job})
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
                chat, message_count, verified = cast(
                    PromptaUIServer, self.server
                ).probe_conversation(conversation_id)
            except KeyError:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            except Exception as exc:
                logger.exception(
                    "Prompta UI activity probe failed conversation=%s", conversation_id
                )
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._json(
                {
                    "ok": True,
                    "chat": chat,
                    "message_count": message_count,
                    "verified": verified,
                }
            )
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
        if (
            not conversation_id
            or server.store.conversation(conversation_id, include_state_events=False) is None
        ):
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
    """Ask systemd to start the durable schedule producer."""

    try:
        started = subprocess.run(
            ["systemctl", "--user", "start", "prompta-scheduler.service"],
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
    orphaned = 0 if preserve_active else _reconcile_orphaned_local_chats(cache_path, state_path)
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
    logger.info("Enqueuing replies for prompta-delivery-worker.service")
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
