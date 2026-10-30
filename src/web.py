"""Local jobs-only web UI for Prompta."""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import mimetypes
import os
import re
import socket
import subprocess
import time
from collections.abc import Mapping
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from .core import DEFAULT_JOBS_PATH, DEFAULT_STATE_PATH
from .delivery_queue import DeliveryQueueStore
from .image_store import ImageStore, image_refs
from .live_events import LocalEventSignals
from .manual_reply_dispatch import ManualReplyDispatcher
from .reply_contracts import ManualReplyStore, ReplyConflict, ReplyIntent
from .response_store import ResponseStore
from .scheduler_service import DurableSchedulerProducer
from .service_health import ServiceHealthStore, browser_page_count, notify_watchdog
from .strict_types import json_object
from .web_jobs import WebJobService

logger = logging.getLogger(__name__)
_STATIC_ROOT = Path(__file__).with_name("static")
_ALLOWED_STATIC = {
    "app.js",
    "app.css",
    "chat-workspace.css",
    "icon.svg",
    "icon-maskable.svg",
    "icon-192.png",
    "icon-512.png",
    "icon-maskable-512.png",
    "apple-touch-icon.png",
    "screenshot-mobile.png",
    "screenshot-wide.png",
    "manifest.webmanifest",
    "sw.js",
}


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


def _start_scheduler_service() -> bool:
    try:
        completed = subprocess.run(
            ["systemctl", "--user", "start", "prompta-scheduler.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return completed.returncode == 0


class PromptaJobServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        *,
        state_path: Path = DEFAULT_STATE_PATH,
        jobs_path: Path = DEFAULT_JOBS_PATH,
    ) -> None:
        super().__init__(address, PromptaJobHandler)
        self.state_path = state_path.expanduser()
        self.jobs_path = jobs_path.expanduser()
        self.live_events = LocalEventSignals(self.jobs_path, self.state_path)
        host = socket.gethostname().strip() or "localhost"
        self.host_name = host.split(".", 1)[0]
        self.health = ServiceHealthStore(self.state_path)
        self.queue = DeliveryQueueStore(self.state_path.parent / "ui-send-jobs.sqlite3")
        self.queue_view = DurableSchedulerProducer(self.state_path, self.jobs_path)
        self.results = ResponseStore(self.state_path.parent / "chat-results.sqlite3")
        self.replies = ManualReplyStore(self.state_path.parent / "chat-results.sqlite3")
        self.replies.recover_orphans()
        self.reply_dispatch = ManualReplyDispatcher(self.replies, self.state_path)
        self.images = ImageStore(self.state_path.parent)
        self.jobs = WebJobService(
            self.jobs_path,
            self.state_path,
            self.host_name,
            start_scheduler=_start_scheduler_service,
        )
        self._last_health_beat = 0.0
        self.health.beat("ui")

    def service_actions(self) -> None:
        super().service_actions()
        now = time.time()
        if now - self._last_health_beat < 5.0:
            return
        self.health.beat("ui", now=now)
        self.replies.recover_orphans(now=now)
        try:
            self.reply_dispatch.pump_queued()
        except Exception as exc:
            logger.warning("Queued follow-up scan failed error_type=%s", type(exc).__name__)
        notify_watchdog()
        self._last_health_beat = now

    def health_payload(self) -> dict[str, object]:
        now = time.time()
        debugger_address = os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9222")
        browser_reachable, page_count = browser_page_count(debugger_address)
        if browser_reachable:
            self.health.beat("browser", now=now)
        services = self.health.snapshot(now=now)
        issues = [
            service + " heartbeat stale"
            for service, snapshot in services.items() if snapshot["stale"] is True
        ]
        if not browser_reachable:
            issues.append("ChatGPT browser unreachable")
        recovery = self.results.recovery_metrics(now=now)
        read_backoff_seconds, _attempts = self.queue_view.runtime.read_backoff_status()
        recovery["account_read_backoff_seconds"] = int(read_backoff_seconds + 0.999)
        return {
            "ok": True,  # The UI HTTP endpoint is alive; preserve watchdog semantics.
            "ready": not issues,
            "issues": issues,
            "server": self.host_name,
            "services": services,
            "browser": {"reachable": browser_reachable, "page_count": page_count},
            "queue": self.queue.health_metrics(now=now),
            "recovery": recovery,
        }


class PromptaJobHandler(BaseHTTPRequestHandler):
    server: PromptaJobServer
    protocol_version = "HTTP/1.1"

    def log_message(self, format: str, *args: object) -> None:
        if urlparse(self.path).path.startswith(("/api/results", "/api/images", "/api/local-chat-pins", "/api/local-chat-reads", "/api/queue-status", "/api/chats/requests")):
            # Search terms and run identifiers can be sensitive; don't log request URLs.
            logger.info("%s - %s /api/results", self.address_string(), self.command)
            return
        logger.info("%s - %s", self.address_string(), format % args)

    def _headers(self, status: HTTPStatus, content_type: str, length: int) -> None:
        self.send_response(status)
        self.send_header("content-type", content_type)
        self.send_header("content-length", str(length))
        self.send_header("cache-control", "no-store")
        self.send_header("x-content-type-options", "nosniff")
        self.end_headers()

    def _write(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        self._headers(status, content_type, len(body))
        if self.command != "HEAD":
            self.wfile.write(body)

    def _json(self, payload: Mapping[str, object], status: HTTPStatus = HTTPStatus.OK) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        self._write(status, "application/json; charset=utf-8", body)

    def _index(self) -> None:
        text = (_STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        text = text.replace("__PROMPTA_SERVER_NAME__", self.server.host_name)
        self._write(HTTPStatus.OK, "text/html; charset=utf-8", text.encode("utf-8"))

    def _static(self, name: str) -> None:
        if name not in _ALLOWED_STATIC:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        path = _STATIC_ROOT / name
        if not path.is_file():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        content = path.read_bytes()
        if name == "sw.js":
            content = content.replace(b"__PROMPTA_UI_HEAD__", _git_short_head().encode("ascii"))
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix in {".js", ".css", ".svg", ".webmanifest"}:
            content_type += "; charset=utf-8"
        self._write(HTTPStatus.OK, content_type, content)

    def _json_body(self, *, max_bytes: int = 1024 * 1024) -> dict[str, object]:
        try:
            length = int(self.headers.get("content-length") or "0")
        except ValueError as exc:
            raise ValueError("Invalid content length") from exc
        if length <= 0 or length > max_bytes:
            raise ValueError("Invalid request body size")
        try:
            payload = json_object(self.rfile.read(length), label="request body")
        except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("Request body must be valid JSON") from exc
        return payload

    def _event_stream(self) -> None:
        """Invalidate local views on storage changes; every reconnect starts with a full sync."""
        self.send_response(HTTPStatus.OK)
        self.send_header("content-type", "text/event-stream; charset=utf-8")
        self.send_header("cache-control", "no-cache, no-transform")
        self.send_header("x-accel-buffering", "no")
        self.send_header("x-content-type-options", "nosniff")
        self.send_header("transfer-encoding", "chunked")
        self.end_headers()

        def emit(payload: str) -> None:
            data = payload.encode("utf-8")
            self.wfile.write(f"{len(data):x}\r\n".encode("ascii") + data + b"\r\n")
            self.wfile.flush()

        def event(topic: str) -> None:
            emit(f"id: {time.time_ns()}\nevent: {topic}\ndata: refresh\n\n")

        try:
            previous = self.server.live_events.snapshot()

            def job_digest() -> bytes:
                # Health heartbeats write to the same runtime database; do not
                # wake the Jobs UI unless its actual payload changed.
                payload = json.dumps(
                    self.server.jobs.scheduled_jobs(),
                    sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                ).encode("utf-8")
                return hashlib.blake2b(payload, digest_size=16).digest()

            previous_jobs = job_digest()
            emit("retry: 1500\n\n")
            event("sync")
            last_heartbeat = time.monotonic()
            while True:
                time.sleep(0.75)
                current = self.server.live_events.snapshot()
                if current.jobs != previous.jobs:
                    current_jobs = job_digest()
                    if current_jobs != previous_jobs:
                        event("jobs")
                    previous_jobs = current_jobs
                if current.chats != previous.chats:
                    event("chats")
                previous = current
                if time.monotonic() - last_heartbeat >= 15:
                    emit(": heartbeat\n\n")
                    last_heartbeat = time.monotonic()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
            # A closed EventSource is normal; avoid logging private request state.
            return

    def do_HEAD(self) -> None:
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path in {"", "/"}:
            self._index()
            return
        if path == "/api/events":
            if self.command == "HEAD":
                self._write(HTTPStatus.OK, "text/event-stream; charset=utf-8", b"")
            else:
                self._event_stream()
            return
        if path == "/api/jobs":
            self._json(self.server.jobs.scheduled_jobs())
            return
        if path.startswith("/api/chats/requests/"):
            # Local-only acknowledgement lookup; never opens ChatGPT or resends.
            request_id = path[len("/api/chats/requests/"):]
            if not re.fullmatch(r"[0-9a-f]{32}", request_id):
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            record = self.server.queue.get("manual-" + request_id)
            if record is None or record["client_id"] not in (
                "manual:" + request_id, "manual:once:" + request_id,
            ):
                self._json({"error": "Queue request not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json({"send_id": record["send_id"], "status": record["status"]})
            return
        if path.startswith("/api/images/"):
            ref = unquote(path[len("/api/images/"):])
            try:
                mime, body = self.server.images.read(ref)
            except ValueError:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            self._write(HTTPStatus.OK, mime, body)
            return
        if path == "/api/health":
            self._json(self.server.health_payload())
            return
        if path == "/api/local-chat-pins":
            pinned = self.server.results.local_pinned_runs()
            self.server.replies.annotate_response_markers(pinned)
            self.server.results.annotate_local_reads(pinned)
            self._json({"items": pinned})
            return
        if path == "/api/queue-status":
            self._json(self.server.queue_view.concurrency_queue_snapshot())
            return
        if path == "/api/results":
            params = parse_qs(parsed.query, keep_blank_values=True)
            try:
                if any(len(values) != 1 for values in params.values()):
                    raise ValueError("Invalid result query")
                if set(params) - {"limit", "offset", "q", "status"}:
                    raise ValueError("Unknown result query")
                limit = int(params.get("limit", ["20"])[0])
                offset = int(params.get("offset", ["0"])[0])
                payload = self.server.results.page(
                    limit=limit, offset=offset, query=params.get("q", [""])[0].strip(),
                    status=params.get("status", [""])[0],
                )
                self.server.replies.annotate_response_markers(payload["items"])
                self.server.results.annotate_local_reads(payload["items"])
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            self._json(payload)
            return
        if path.startswith("/api/results/") and path.endswith("/turns"):
            send_id = unquote(path[len("/api/results/"):-len("/turns")])
            if not send_id or "/" in send_id:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            turns = self.server.replies.turns(send_id)
            if turns is None:
                self._json({"error": "Run not found"}, HTTPStatus.NOT_FOUND)
            else:
                self._json({"turns": turns})
            return
        if path.startswith("/api/results/"):
            send_id = unquote(path[len("/api/results/"):])
            if "/" in send_id:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            record = self.server.results.detail(send_id)
            if record is None:
                self._json({"error": "Run not found"}, HTTPStatus.NOT_FOUND)
            else:
                self.server.replies.annotate_response_markers([record])
                self.server.results.annotate_local_reads([record])
                queued = self.server.queue.get(send_id)
                record["images"] = [
                    {"name": ref.split("/", 1)[1], "url": "./api/images/" + ref}
                    for ref in image_refs(queued["images"])
                ] if queued is not None else []
                self._json(record)
            return
        if path.startswith("/") and path[1:] in _ALLOWED_STATIC:
            self._static(path[1:])
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        reply_path = path.startswith("/api/results/") and path.endswith("/reply-intents")
        send_reply_path = path.startswith("/api/results/") and path.endswith("/reply-send")
        recover_reply_path = path.startswith("/api/results/") and path.endswith("/reply-recover")
        queue_reply_path = path.startswith("/api/results/") and path.endswith("/reply-queue")
        if path not in {"/api/jobs", "/api/images", "/api/chats", "/api/local-chat-pins", "/api/local-chat-pins/import", "/api/local-chat-reads", "/api/local-chat-reads/import", "/api/local-chat-reads/all"} and not (
            reply_path or send_reply_path or recover_reply_path or queue_reply_path
        ):
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            if reply_path or send_reply_path or recover_reply_path or queue_reply_path:
                suffix = (
                    "/reply-recover" if recover_reply_path
                    else "/reply-queue" if queue_reply_path
                    else "/reply-send" if send_reply_path else "/reply-intents"
                )
                send_id = unquote(path[len("/api/results/"):-len(suffix)])
                if not send_id or "/" in send_id:
                    self.send_error(HTTPStatus.NOT_FOUND)
                    return
                if self.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                    raise ValueError("Reply contract requires JSON")
                payload = self._json_body(max_bytes=65536)
                if recover_reply_path:
                    if payload:
                        raise ValueError("Reply recovery does not accept message content")
                    recovered = self.server.reply_dispatch.recover(send_id)
                    self._json({"ok": True, **recovered})
                    return
                if queue_reply_path:
                    if set(payload) != {"reply_id", "text"}:
                        raise ValueError("Invalid queued follow-up fields")
                    reply_id, text = payload["reply_id"], payload["text"]
                    if not isinstance(reply_id, str) or not isinstance(text, str):
                        raise ValueError("Invalid queued follow-up fields")
                    turn = self.server.replies.queue_followup(send_id, reply_id, text)
                    self._json({"ok": True, "turn": turn}, HTTPStatus.ACCEPTED)
                    self.server.reply_dispatch.pump_queued()
                    return
                intent = ReplyIntent.parse(payload)
                if send_reply_path:
                    turn = self.server.reply_dispatch.submit(send_id, intent)
                    self._json(
                        {"ok": True, "dispatched": False, "queued_for_explicit_dispatch": turn["status"] == "prepared", "turn": turn},
                        HTTPStatus.ACCEPTED,
                    )
                else:
                    turn = self.server.replies.prepare(send_id, intent)
                    self._json({"ok": True, "dispatched": False, "turn": turn}, HTTPStatus.ACCEPTED)
                return
            if path in {"/api/local-chat-reads", "/api/local-chat-reads/import", "/api/local-chat-reads/all"}:
                if self.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                    raise ValueError("Local read changes require JSON")
                payload = self._json_body(max_bytes=786432 if path.endswith("/import") else 1024)
                if path.endswith("/all"):
                    if payload:
                        raise ValueError("Mark all read accepts no fields")
                    count = self.server.replies.mark_all_local_read()
                    self._json({"ok": True, "count": count})
                    return
                if path.endswith("/import"):
                    raw_reads = payload.get("reads")
                    if set(payload) != {"reads"} or not isinstance(raw_reads, dict):
                        raise ValueError("Invalid legacy read import")
                    reads: dict[str, str] = {}
                    for send_id, revision in raw_reads.items():
                        if not isinstance(send_id, str) or not isinstance(revision, str):
                            raise ValueError("Invalid legacy read import")
                        reads[send_id] = revision
                    self.server.results.import_legacy_local_reads(reads)
                else:
                    send_id, revision = payload.get("send_id"), payload.get("revision")
                    if set(payload) != {"send_id", "revision"} or not isinstance(send_id, str) or not isinstance(revision, str):
                        raise ValueError("Invalid local read receipt")
                    record = self.server.results.detail(send_id)
                    if record is None:
                        self._json({"ok": False, "error": "Local run not found"}, HTTPStatus.NOT_FOUND)
                        return
                    self.server.replies.annotate_response_markers([record])
                    if not revision or record["last_reply_revision"] != revision:
                        self._json({"ok": False, "error": "Reply revision changed"}, HTTPStatus.CONFLICT)
                        return
                    self.server.results.mark_local_read(send_id, revision)
                self._json({"ok": True})
                return
            if path in {"/api/local-chat-pins", "/api/local-chat-pins/import"}:
                if self.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/json":
                    raise ValueError("Local pin changes require JSON")
                payload = self._json_body(max_bytes=8192)
                if path.endswith("/import"):
                    raw_ids = payload.get("send_ids")
                    if set(payload) != {"send_ids"} or not isinstance(raw_ids, list):
                        raise ValueError("Invalid legacy pin import")
                    ids: list[str] = []
                    for item in raw_ids:
                        if not isinstance(item, str):
                            raise ValueError("Invalid legacy pin import")
                        ids.append(item)
                    self.server.results.import_legacy_local_pins(ids)
                else:
                    send_id, pinned = payload.get("send_id"), payload.get("pinned")
                    if set(payload) != {"send_id", "pinned"} or not isinstance(send_id, str) or not isinstance(pinned, bool):
                        raise ValueError("Invalid local pin change")
                    if not self.server.results.set_local_pin(send_id, pinned=pinned):
                        self._json({"ok": False, "error": "Local run not found"}, HTTPStatus.NOT_FOUND)
                        return
                self._json({"ok": True})
                return
            payload = self._json_body(max_bytes=11 * 1024 * 1024 if path == "/api/images" else 1024 * 1024)
            if path == "/api/chats":
                if set(payload) != {"request_id", "prompt", "images"}:
                    raise ValueError("Invalid fresh chat fields")
                request_id, prompt, raw_images = (
                    payload["request_id"], payload["prompt"], payload["images"]
                )
                if (
                    not isinstance(request_id, str) or not isinstance(prompt, str)
                    or not prompt.strip() or len(prompt) > 32000
                    or not isinstance(raw_images, list) or len(raw_images) > 4
                ):
                    raise ValueError("Invalid fresh chat payload")
                refs = image_refs(raw_images)
                if len(refs) != len(raw_images):
                    raise ValueError("Invalid image references")
                for ref in refs:
                    self.server.images.path(ref)
                receipt = self.server.queue.enqueue_manual(
                    prompt.strip(), images=refs, request_id=request_id,
                    pin_local_default=True,
                )
                self._json(
                    {"ok": True, "send_id": receipt["send_id"], "status": receipt["status"]},
                    HTTPStatus.ACCEPTED,
                )
                return
            if path == "/api/images":
                name, data = payload.get("name"), payload.get("data")
                if not isinstance(name, str) or not isinstance(data, str):
                    raise ValueError("Invalid image upload")
                ref = self.server.images.save(name, data)
                self._json({"ok": True, "image": {"ref": ref, "name": ref.split("/", 1)[1], "url": "./api/images/" + ref}})
                return
            action = str(payload.get("action") or "")
            result = self.server.jobs.apply(action, payload)
        except ReplyConflict as exc:
            self._json({"ok": False, "error": str(exc)}, HTTPStatus.CONFLICT)
            return
        except ValueError as exc:
            self._json({"ok": False, "error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return
        except Exception as exc:
            if reply_path or send_reply_path or recover_reply_path or queue_reply_path or path == "/api/chats" or path.startswith(("/api/local-chat-pins", "/api/local-chat-reads")):
                # DB/driver exceptions may contain secret prompts or SQLite parameters.
                logger.error("Chat send contract failed error_type=%s", type(exc).__name__)
                self._json({"ok": False, "error": "Chat send contract unavailable"},
                           HTTPStatus.INTERNAL_SERVER_ERROR)
                return
            logger.exception("Prompta jobs update failed")
            self._json(
                {"ok": False, "error": str(exc) or exc.__class__.__name__},
                HTTPStatus.INTERNAL_SERVER_ERROR,
            )
            return
        self._json(result)


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    state_path: Path = DEFAULT_STATE_PATH,
    jobs_path: Path = DEFAULT_JOBS_PATH,
) -> None:
    server = PromptaJobServer((host, port), state_path=state_path, jobs_path=jobs_path)
    logger.info("Prompta jobs UI listening on http://%s:%d", host, port)
    notify_watchdog()
    try:
        server.serve_forever(poll_interval=0.5)
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Prompta jobs web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    serve(host=args.host, port=args.port, state_path=args.state, jobs_path=args.jobs_file)


if __name__ == "__main__":
    main()
