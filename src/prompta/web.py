"""Local web UI for Prompta's cached conversations and live replies."""

from __future__ import annotations

import argparse
import asyncio
import base64
import json
import logging
import mimetypes
import shlex
import sqlite3
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlparse

from .cache import DEFAULT_CACHE_PATH
from .core import (
    DEFAULT_STATE_PATH,
    _daemon_is_running,
    _send_direct,
    _send_once_via_control,
    _send_reply_via_control,
)

logger = logging.getLogger(__name__)
_STATIC_ROOT = Path(__file__).with_name("static")


class ReadOnlyChatStore:
    """Open fresh read-only data sources for each web request."""

    def __init__(self, path: Path = DEFAULT_CACHE_PATH, log_path: Path | None = None) -> None:
        self.path = path.expanduser()
        self.log_path = (
            log_path.expanduser()
            if log_path is not None
            else self.path.with_name("prompta-glass.log")
        )

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        connection = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=2.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=2000")
        return connection

    def conversations(self, *, limit: int = 200, query: str = "") -> list[dict[str, Any]]:
        search = query.strip()
        where = ""
        parameters: list[Any] = []
        if search:
            where = """
                WHERE c.title LIKE ? COLLATE NOCASE
                   OR c.job_name LIKE ? COLLATE NOCASE
                   OR c.prompt LIKE ? COLLATE NOCASE
                   OR EXISTS (
                       SELECT 1 FROM messages sm
                       WHERE sm.conversation_id = c.id
                         AND sm.message_key NOT LIKE 'request-placeholder-%'
                         AND sm.content LIKE ? COLLATE NOCASE
                   )
            """
            needle = f"%{search}%"
            parameters.extend([needle, needle, needle, needle])
        parameters.append(max(1, min(limit, 500)))
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        c.id,
                        c.job_name,
                        c.url,
                        c.title,
                        c.status,
                        c.created_at,
                        c.updated_at,
                        c.completed_at,
                        COALESCE(
                            (
                                SELECT m.content FROM messages m
                                WHERE m.conversation_id = c.id
                                  AND m.message_key NOT LIKE 'request-placeholder-%'
                                ORDER BY m.ordinal DESC LIMIT 1
                            ),
                            NULLIF(c.prompt, '')
                        ) AS preview,
                        CASE
                            WHEN EXISTS (
                                SELECT 1 FROM messages m
                                WHERE m.conversation_id = c.id
                                  AND m.message_key NOT LIKE 'request-placeholder-%'
                            )
                            THEN (
                                SELECT COUNT(*) FROM messages m
                                WHERE m.conversation_id = c.id
                                  AND m.message_key NOT LIKE 'request-placeholder-%'
                            )
                            WHEN TRIM(c.prompt) <> '' THEN 1
                            ELSE 0
                        END AS message_count
                    FROM conversations c
                    {where}
                    ORDER BY
                        CASE c.status WHEN 'active' THEN 0 ELSE 1 END,
                        c.updated_at DESC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()
        except FileNotFoundError:
            return []
        return [dict(row) for row in rows]

    def conversation(self, conversation_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                conversation = connection.execute(
                    """
                    SELECT id, job_name, prompt, url, title, status,
                           created_at, updated_at, completed_at
                    FROM conversations
                    WHERE id = ?
                    """,
                    (conversation_id,),
                ).fetchone()
                if conversation is None:
                    return None
                messages = connection.execute(
                    """
                    SELECT message_key, ordinal, role, content, status,
                           created_at, updated_at
                    FROM messages
                    WHERE conversation_id = ?
                      AND message_key NOT LIKE 'request-placeholder-%'
                    ORDER BY ordinal
                    """,
                    (conversation_id,),
                ).fetchall()
        except FileNotFoundError:
            return None
        payload = dict(conversation)
        message_payloads = [dict(message) for message in messages]
        prompt = str(payload.get("prompt") or "")
        if not message_payloads and prompt.strip():
            message_payloads = [
                {
                    "message_key": "__prompta_prompt__",
                    "ordinal": 0,
                    "role": "user",
                    "content": prompt,
                    "status": "complete",
                    "created_at": payload["created_at"],
                    "updated_at": payload["updated_at"],
                }
            ]
        payload["messages"] = message_payloads
        return payload

    def logs(self, *, limit: int = 500) -> dict[str, Any]:
        if not self.log_path.is_file():
            return {"exists": False, "lines": [], "updated_at": None}
        try:
            text = self.log_path.read_text(errors="replace")
            updated_at = self.log_path.stat().st_mtime
        except OSError:
            return {"exists": False, "lines": [], "updated_at": None}
        lines = text.splitlines()[-max(1, min(limit, 2000)) :]
        return {"exists": True, "lines": lines, "updated_at": updated_at}

    def stats(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"exists": False, "total": 0, "active": 0}
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active
                    FROM conversations
                    """
                ).fetchone()
        except (FileNotFoundError, sqlite3.Error):
            return {"exists": False, "total": 0, "active": 0}
        return {
            "exists": True,
            "total": int(row["total"] or 0),
            "active": int(row["active"] or 0),
        }

    def event_fingerprint(self) -> tuple[int, float, int, float, str]:
        "Return a cheap cache revision for event-driven UI refreshes."
        if not self.path.is_file():
            return (0, 0.0, 0, 0.0, "")
        try:
            with self._connect() as connection:
                row = connection.execute(
                    "SELECT "
                    "(SELECT COUNT(*) FROM conversations) AS conversation_count, "
                    "COALESCE((SELECT MAX(updated_at) FROM conversations), 0) "
                    "AS conversation_updated, "
                    "(SELECT COUNT(*) FROM messages "
                    "WHERE message_key NOT LIKE 'request-placeholder-%') AS message_count, "
                    "COALESCE((SELECT MAX(updated_at) FROM messages "
                    "WHERE message_key NOT LIKE 'request-placeholder-%'), 0) "
                    "AS message_updated, "
                    "(SELECT id FROM conversations ORDER BY updated_at DESC LIMIT 1) "
                    "AS latest_conversation_id"
                ).fetchone()
        except (FileNotFoundError, sqlite3.Error):
            return (0, 0.0, 0, 0.0, "")
        return (
            int(row["conversation_count"] or 0),
            float(row["conversation_updated"] or 0.0),
            int(row["message_count"] or 0),
            float(row["message_updated"] or 0.0),
            str(row["latest_conversation_id"] or ""),
        )


_REMOTE_CONTROL_TIMEOUT_SECONDS = 11 * 60


def _remote_control(
    control_host: str,
    *,
    operation: str,
    message: str,
    conversation_id: str = "",
) -> str:
    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "operation": operation,
                "message": message,
                "conversation_id": conversation_id,
            },
            ensure_ascii=False,
        ).encode("utf-8")
    ).decode("ascii")
    code = """
import asyncio
import base64
import json
import sys
from prompta.core import DEFAULT_STATE_PATH, _send_once_via_control, _send_reply_via_control

payload = json.loads(base64.urlsafe_b64decode(sys.argv[1]).decode("utf-8"))
try:
    if payload["operation"] == "once":
        result = asyncio.run(_send_once_via_control(DEFAULT_STATE_PATH, payload["message"]))
    else:
        result = asyncio.run(
            _send_reply_via_control(
                DEFAULT_STATE_PATH,
                payload["conversation_id"],
                payload["message"],
            )
        )
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
else:
    print(json.dumps({"ok": True, "conversation_id": result}, ensure_ascii=False))
""".strip()
    remote_command = shlex.join(
        ["/home/brandon/prompta/.venv/bin/python", "-c", code, payload]
    )
    completed = subprocess.run(
        [
            "ssh",
            "-F",
            str(Path.home() / ".ssh" / "config"),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            control_host,
            remote_command,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=_REMOTE_CONTROL_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        detail = (completed.stderr or completed.stdout or "remote control failed").strip()
        raise RuntimeError(detail[-2000:])
    result = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    if not result:
        raise RuntimeError("remote Prompta control returned an empty conversation id")
    try:
        response = json.loads(result)
    except json.JSONDecodeError:
        return result
    if not isinstance(response, dict):
        raise RuntimeError("remote Prompta control returned an invalid response")
    if response.get("ok") is not True:
        raise RuntimeError(str(response.get("error") or "remote Prompta control failed"))
    conversation_id = str(response.get("conversation_id") or "")
    if not conversation_id:
        raise RuntimeError("remote Prompta control returned an empty conversation id")
    return conversation_id


class SendJobRegistry:
    """Run UI sends off-request and expose their status for polling."""

    def __init__(self, sender: Callable[[str, str, str], str]) -> None:
        self._sender = sender
        self._jobs: dict[str, dict[str, Any]] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        *,
        operation: str,
        message: str,
        conversation_id: str = "",
    ) -> dict[str, Any]:
        send_id = uuid.uuid4().hex
        now = time.time()
        job = {
            "send_id": send_id,
            "operation": operation,
            "status": "queued",
            "conversation_id": conversation_id,
            "error": "",
            "created_at": now,
            "updated_at": now,
        }
        with self._lock:
            cutoff = now - 3600.0
            self._jobs = {
                key: value
                for key, value in self._jobs.items()
                if float(value.get("updated_at") or 0.0) >= cutoff
            }
            self._jobs[send_id] = job
        threading.Thread(
            target=self._run,
            args=(send_id, operation, message, conversation_id),
            name=f"prompta-ui-send-{send_id[:8]}",
            daemon=True,
        ).start()
        return dict(job)

    def get(self, send_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(send_id)
            return dict(job) if job is not None else None

    def _update(self, send_id: str, **updates: Any) -> None:
        with self._lock:
            job = self._jobs.get(send_id)
            if job is None:
                return
            job.update(updates)
            job["updated_at"] = time.time()

    def _run(
        self,
        send_id: str,
        operation: str,
        message: str,
        conversation_id: str,
    ) -> None:
        self._update(send_id, status="running")
        try:
            result = self._sender(operation, message, conversation_id)
        except Exception as exc:
            logger.exception(
                "Prompta UI background send failed send_id=%s operation=%s conversation=%s",
                send_id,
                operation,
                conversation_id or "new",
            )
            self._update(send_id, status="failed", error=str(exc))
            return
        self._update(
            send_id,
            status="succeeded",
            conversation_id=result,
            error="",
        )


class PromptaUIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        store: ReadOnlyChatStore,
        state_path: Path = DEFAULT_STATE_PATH,
        control_host: str = "",
    ) -> None:
        super().__init__(address, PromptaUIHandler)
        self.store = store
        self.state_path = state_path.expanduser()
        self.control_host = control_host.strip()
        self._local_send_lock = threading.Lock()
        self.send_jobs = SendJobRegistry(self._send)

    def _send(self, operation: str, message: str, conversation_id: str) -> str:
        if self.control_host:
            return _remote_control(
                self.control_host,
                operation=operation,
                message=message,
                conversation_id=conversation_id,
            )
        with self._local_send_lock:
            if _daemon_is_running(self.state_path):
                if operation == "once":
                    return asyncio.run(_send_once_via_control(self.state_path, message))
                return asyncio.run(
                    _send_reply_via_control(self.state_path, conversation_id, message)
                )
            logger.info("Prompta scheduler is stopped; using a direct local browser send")
            return asyncio.run(
                _send_direct(
                    self.state_path,
                    self.store.path,
                    message,
                    conversation_id=conversation_id if operation == "reply" else "",
                )
            )


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

    @property
    def control_host(self) -> str:
        return cast(PromptaUIServer, self.server).control_host

    @property
    def send_jobs(self) -> SendJobRegistry:
        return cast(PromptaUIServer, self.server).send_jobs

    def _message_from_json_body(self) -> str | None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.casefold().startswith("application/json"):
            self._json({"error": "Expected application/json"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return None
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > 64 * 1024:
            self._json({"error": "Invalid message size"}, HTTPStatus.BAD_REQUEST)
            return None
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json({"error": "Invalid JSON body"}, HTTPStatus.BAD_REQUEST)
            return None
        message = str(payload.get("message") or "") if isinstance(payload, dict) else ""
        if not message.strip():
            self._json({"error": "Message is empty"}, HTTPStatus.BAD_REQUEST)
            return None
        return message

    def _headers(self, status: HTTPStatus, content_type: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
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

    def _json(self, payload: Any, status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self._headers(status, "application/json; charset=utf-8")
        self.wfile.write(body)

    def _event_stream(self) -> None:
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream; charset=utf-8")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("X-Accel-Buffering", "no")
        self.end_headers()

        last_fingerprint = self.store.event_fingerprint()
        last_heartbeat = time.monotonic()
        try:
            while True:
                fingerprint = self.store.event_fingerprint()
                now = time.monotonic()
                if fingerprint != last_fingerprint:
                    payload = json.dumps(
                        {
                            "revision": fingerprint[:4],
                            "conversation_id": fingerprint[4],
                        },
                        separators=(",", ":"),
                    )
                    body = "event: refresh\ndata: " + payload + "\n\n"
                    self.wfile.write(body.encode())
                    self.wfile.flush()
                    last_fingerprint = fingerprint
                    last_heartbeat = now
                elif now - last_heartbeat >= 15.0:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_heartbeat = now
                time.sleep(0.75)
        except (BrokenPipeError, ConnectionResetError):
            return

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
        self._headers(HTTPStatus.OK, f"{mime}; charset=utf-8" if mime.startswith("text/") else mime)
        self.wfile.write(body)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._static("index.html", "text/html")
            return
        if path == "/app.css":
            self._static("app.css", "text/css")
            return
        if path == "/app.js":
            self._static("app.js", "text/javascript")
            return
        if path == "/api/health":
            self._json(self.store.stats())
            return
        if path == "/api/events":
            self._event_stream()
            return
        if path == "/api/chats":
            query = parse_qs(parsed.query)
            search = query.get("q", [""])[0]
            try:
                limit = int(query.get("limit", ["200"])[0])
            except ValueError:
                limit = 200
            self._json({"chats": self.store.conversations(limit=limit, query=search)})
            return
        if path == "/api/logs":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["500"])[0])
            except ValueError:
                limit = 500
            self._json(self.store.logs(limit=limit))
            return
        send_prefix = "/api/sends/"
        if path.startswith(send_prefix):
            send_id = unquote(path[len(send_prefix) :]).strip("/")
            job = self.send_jobs.get(send_id)
            if job is None:
                self._json({"error": "Send not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(job)
            return
        prefix = "/api/chats/"
        if path.startswith(prefix):
            conversation_id = unquote(path[len(prefix) :])
            chat = self.store.conversation(conversation_id)
            if chat is None:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(chat)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/chats":
            message = self._message_from_json_body()
            if message is None:
                return
            job = self.send_jobs.submit(
                operation="once",
                message=message,
            )
            self._json({"ok": True, **job}, HTTPStatus.ACCEPTED)
            return

        prefix = "/api/chats/"
        suffix = "/messages"
        if not (path.startswith(prefix) and path.endswith(suffix)):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        conversation_id = unquote(path[len(prefix) : -len(suffix)]).strip("/")
        if not conversation_id or self.store.conversation(conversation_id) is None:
            self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
            return

        message = self._message_from_json_body()
        if message is None:
            return

        job = self.send_jobs.submit(
            operation="reply",
            conversation_id=conversation_id,
            message=message,
        )
        self._json({"ok": True, **job}, HTTPStatus.ACCEPTED)


def serve(
    cache_path: Path,
    log_path: Path | None,
    host: str,
    port: int,
    state_path: Path = DEFAULT_STATE_PATH,
    control_host: str = "",
) -> None:
    store = ReadOnlyChatStore(cache_path, log_path)
    server = PromptaUIServer((host, port), store, state_path, control_host)
    logger.info("Prompta UI listening on http://%s:%d", host, port)
    logger.info("Reading cache %s in SQLite query-only mode", cache_path.expanduser())
    if control_host:
        logger.info("Sending replies through Prompta on SSH host %s", control_host)
    else:
        logger.info(
            "Sending replies locally via scheduler control when available, direct browser otherwise"
        )
    logger.info("Reading logs from %s", store.log_path)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Prompta's local conversation UI")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--control-host", default="")
    parser.add_argument("--logs", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    serve(
        args.cache,
        args.logs,
        args.host,
        max(1, min(args.port, 65535)),
        args.state,
        args.control_host,
    )


if __name__ == "__main__":
    main()
