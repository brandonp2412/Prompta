"""FastAPI HTTP boundary for private local job management and results."""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import logging
import mimetypes
import os
import socket
import subprocess
import time
from collections.abc import AsyncGenerator, AsyncIterator
from contextlib import asynccontextmanager, suppress
from pathlib import Path

import uvicorn
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from pydantic import BaseModel, Field
from sse_starlette import EventSourceResponse, ServerSentEvent
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException

from .config import DEFAULT_CONFIG_PATH, ConnectorApproval, ParallelismSettings
from .core import DEFAULT_JOBS_PATH, DEFAULT_STATE_PATH
from .delivery_queue import DeliveryQueueStore
from .image_store import ImageStore
from .live_events import LiveRevisions, LocalEventSignals
from .logging_config import configure_logging
from .manual_reply_dispatch import ManualReplyDispatcher
from .reply_contracts import ManualReplyStore, ReplyConflict
from .response_store import ResponseStore
from .scheduler_service import DurableSchedulerProducer
from .service_health import ServiceHealthStore, browser_page_count, notify_watchdog
from .web_boundary import JSONRoute, RequestBoundary
from .web_chats import register_chat_routes
from .web_jobs import WebJobService
from .web_models import ErrorResponse, JobAction

logger = logging.getLogger(__name__)
_STATIC_ROOT = Path(__file__).with_name("static")
_ALLOWED_STATIC = {
    "app.js",
    "app.css",
    "chat-workspace.css",
    "jobs.css",
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


class WebServices:
    def __init__(
        self,
        *,
        state_path: Path = DEFAULT_STATE_PATH,
        jobs_path: Path = DEFAULT_JOBS_PATH,
    ) -> None:
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
            start_scheduler=(
                (lambda: False)
                if os.environ.get("PROMPTA_DEV_MODE") == "1"
                else _start_scheduler_service
            ),
        )
        self._last_health_beat = 0.0
        self.health.beat("ui")

    def service_actions(self) -> None:
        now = time.time()
        if now - self._last_health_beat < 5.0:
            return
        self.health.beat("ui", now=now)
        self.replies.recover_orphans(now=now)
        # The separate manual-reply worker owns every explicit send and its
        # long-running capture; UI restarts must not terminate those threads.
        if os.environ.get("PROMPTA_DEV_MODE") != "1":
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
            for service, snapshot in services.items()
            if snapshot["stale"] is True
        ]
        if not browser_reachable:
            issues.append("ChatGPT browser unreachable")
        recovery = self.results.recovery_metrics(now=now)
        recovery.update(self.replies.reply_recovery_metrics(now=now))
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
            "admission": self.queue_view.runtime.account_admission_status(),
            "recovery": recovery,
        }


class _ConcurrencyUpdate(BaseModel):
    enabled: bool
    max_workers: int = Field(ge=1, le=128)


class _ApprovalUpdate(BaseModel):
    enabled: bool


class _SettingsUpdate(BaseModel):
    parallelism: _ConcurrencyUpdate
    connector_approval: _ApprovalUpdate


def create_app(
    *,
    state_path: Path = DEFAULT_STATE_PATH,
    jobs_path: Path = DEFAULT_JOBS_PATH,
    services: WebServices | None = None,
) -> FastAPI:
    local = services or WebServices(state_path=state_path, jobs_path=jobs_path)

    async def maintain() -> None:
        while True:
            try:
                await run_in_threadpool(local.service_actions)
            except Exception as exc:
                logger.error("UI maintenance failed error_type=%s", type(exc).__name__)
            await asyncio.sleep(5)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncGenerator[None]:
        task = asyncio.create_task(maintain())
        try:
            yield
        finally:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task

    app = FastAPI(
        title="Prompta",
        lifespan=lifespan,
        responses={
            "4XX": {
                "model": ErrorResponse,
                "description": "Invalid input (400), missing resource (404), unsupported method (405), or conflict (409)",
            },
            500: {"model": ErrorResponse, "description": "Local service unavailable"},
        },
    )
    app.add_middleware(RequestBoundary)
    app.router.route_class = JSONRoute

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Pydantic errors can contain input prompts and tool data. Never echo them.
        return JSONResponse({"ok": False, "error": "Invalid request"}, status_code=400)

    @app.exception_handler(ReplyConflict)
    async def conflict(request: Request, exc: ReplyConflict) -> JSONResponse:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=409)

    @app.exception_handler(ValueError)
    async def invalid_value(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse({"ok": False, "error": str(exc)}, status_code=400)

    @app.exception_handler(StarletteHTTPException)
    async def http_error(request: Request, exc: StarletteHTTPException) -> JSONResponse:
        return JSONResponse(
            {"ok": False, "error": str(exc.detail)},
            status_code=exc.status_code,
            headers=exc.headers,
        )

    @app.api_route(
        "/", methods=["GET", "HEAD"], response_class=HTMLResponse, include_in_schema=False
    )
    def index() -> HTMLResponse:
        text = (_STATIC_ROOT / "index.html").read_text(encoding="utf-8")
        return HTMLResponse(text.replace("__PROMPTA_SERVER_NAME__", local.host_name))

    @app.get(
        "/api/events",
        response_class=EventSourceResponse,
        responses={200: {"content": {"text/event-stream": {}}}},
    )
    async def events() -> EventSourceResponse:
        async def stream() -> AsyncIterator[ServerSentEvent]:
            def digest() -> bytes | None:
                try:
                    payload = json.dumps(
                        local.jobs.scheduled_jobs(),
                        sort_keys=True,
                        separators=(",", ":"),
                        ensure_ascii=False,
                    )
                except Exception as exc:
                    logger.warning("Live jobs snapshot unavailable error_type=%s", type(exc).__name__)
                    return None
                return hashlib.blake2b(payload.encode(), digest_size=16).digest()

            def event(topic: str) -> ServerSentEvent:
                return ServerSentEvent(event=topic, data="refresh", id=str(time.time_ns()))

            previous = await run_in_threadpool(local.live_events.snapshot)
            previous_jobs = await run_in_threadpool(digest)
            yield ServerSentEvent(retry=1500)
            yield event("sync")
            while True:
                await asyncio.sleep(0.75)
                # SQLite snapshots can block during checkpoints; keep them off the event loop.
                current = await run_in_threadpool(local.live_events.snapshot)
                jobs_revision = current.jobs
                if current.jobs != previous.jobs or previous_jobs is None:
                    current_jobs = await run_in_threadpool(digest)
                    if current_jobs is None:
                        # Keep the earlier revision to retry on a later tick.
                        jobs_revision = previous.jobs
                    else:
                        if current_jobs != previous_jobs:
                            yield event("jobs")
                        previous_jobs = current_jobs
                if current.chats != previous.chats:
                    yield event("chats")
                previous = LiveRevisions(jobs=jobs_revision, chats=current.chats)

        return EventSourceResponse(
            stream(),
            ping=15,
            ping_message_factory=lambda: ServerSentEvent(event="ping", data="keepalive"),
            send_timeout=30,
            sep="\n",
            headers={"Cache-Control": "no-cache, no-transform"},
        )

    @app.head("/api/events", include_in_schema=False)
    def events_head() -> Response:
        return Response(media_type="text/event-stream")

    @app.head("/api/jobs", include_in_schema=False)
    @app.get("/api/jobs")
    def jobs() -> dict[str, object]:
        return dict(local.jobs.scheduled_jobs())

    @app.post("/api/jobs")
    def change_jobs(payload: JobAction) -> dict[str, object]:
        return dict(local.jobs.execute(payload))

    @app.head("/api/health", include_in_schema=False)
    @app.get("/api/health")
    def health() -> dict[str, object]:
        return local.health_payload()

    @app.head("/api/queue-status", include_in_schema=False)
    @app.get("/api/queue-status")
    def queue_status() -> dict[str, object]:
        return dict(local.queue_view.concurrency_queue_snapshot())

    @app.post("/api/queue/{send_id}/front")
    def bump_queue(send_id: str) -> dict[str, bool]:
        if not local.queue.bump_to_front(send_id):
            raise HTTPException(409, "This item is no longer waiting in the queue.")
        return {"ok": True}

    @app.post("/api/queue-jobs/{name:path}/front")
    def bump_queued_job(name: str) -> dict[str, bool]:
        for receipt in local.queue.pending_dispatch_metadata():
            client = str(receipt["client_id"])
            if client.startswith("scheduled:") and client.rsplit(":", 1)[-1] == name:
                return bump_queue(str(receipt["send_id"]))
        raise HTTPException(409, "This job is no longer waiting in the queue.")

    @app.get("/api/settings")
    def get_settings() -> dict[str, object]:
        return {
            "parallelism": ParallelismSettings.load(DEFAULT_CONFIG_PATH).model_dump(),
            "connector_approval": ConnectorApproval.load(DEFAULT_CONFIG_PATH).model_dump(),
        }

    @app.put("/api/settings")
    def update_settings(payload: _SettingsUpdate) -> dict[str, object]:
        # Persist exactly the two supported sections, dropping obsolete settings.
        import tempfile

        config_path = DEFAULT_CONFIG_PATH.expanduser()
        config_path.parent.mkdir(parents=True, exist_ok=True)
        original = (
            f"[parallelism]\n"
            f"enabled = {str(payload.parallelism.enabled).lower()}\n"
            f"max_workers = {payload.parallelism.max_workers}\n\n"
            f"[connector_approval]\n"
            f"enabled = {str(payload.connector_approval.enabled).lower()}\n"
        )
        # Validate the complete generated configuration before replacing it.
        import tomllib

        tomllib.loads(original)
        fd, temporary = tempfile.mkstemp(prefix=".config-", dir=config_path.parent)
        try:
            with os.fdopen(fd, "w") as handle:
                handle.write(original)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, config_path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        return get_settings()

    register_chat_routes(app, local)

    @app.api_route("/{name}", methods=["GET", "HEAD"], include_in_schema=False)
    def static(name: str) -> Response:
        path = _STATIC_ROOT / name
        if name not in _ALLOWED_STATIC or not path.is_file():
            raise HTTPException(404)
        content = path.read_bytes()
        if name == "sw.js":
            content = content.replace(b"__PROMPTA_UI_HEAD__", _git_short_head().encode("ascii"))
        media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if path.suffix in {".js", ".css", ".svg", ".webmanifest"}:
            media_type += "; charset=utf-8"
        return Response(content, media_type=media_type)

    return app


def serve(
    *,
    host: str = "127.0.0.1",
    port: int = 8765,
    state_path: Path = DEFAULT_STATE_PATH,
    jobs_path: Path = DEFAULT_JOBS_PATH,
) -> None:
    # Uvicorn access/error tracebacks can expose query strings or database values.
    # Handled failures are logged as exception types at the application boundary.
    uvicorn.run(
        create_app(state_path=state_path, jobs_path=jobs_path),
        host=host,
        port=port,
        access_log=False,
        log_config=None,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Prompta jobs web UI")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    args = parser.parse_args()
    configure_logging("ui")
    serve(host=args.host, port=args.port, state_path=args.state, jobs_path=args.jobs_file)


if __name__ == "__main__":
    main()
