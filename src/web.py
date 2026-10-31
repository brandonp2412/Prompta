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
from collections.abc import AsyncGenerator, AsyncIterator, Callable, Coroutine
from contextlib import asynccontextmanager, suppress
from pathlib import Path
from typing import Annotated

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.routing import APIRoute
from sse_starlette import EventSourceResponse, ServerSentEvent
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .core import DEFAULT_JOBS_PATH, DEFAULT_STATE_PATH
from .delivery_queue import DeliveryQueueStore
from .image_store import ImageStore, image_refs
from .live_events import LocalEventSignals
from .manual_reply_dispatch import ManualReplyDispatcher
from .reply_contracts import ManualReplyStore, ReplyConflict, ReplyIntent
from .response_store import ResponseStore
from .scheduler_service import DurableSchedulerProducer
from .service_health import ServiceHealthStore, browser_page_count, notify_watchdog
from .web_jobs import WebJobService
from .web_models import (
    EmptyRequest,
    ErrorResponse,
    FollowupRequest,
    FreshChatRequest,
    ImageUpload,
    JobAction,
    PinImport,
    PinRequest,
    ReadImport,
    ReadRequest,
    ReplyRequest,
    RequestId,
    ResultsQuery,
)

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
            start_scheduler=_start_scheduler_service,
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


class JSONRoute(APIRoute):
    """Require JSON only after routing has matched an actual POST endpoint."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[object, object, Response]]:
        handler = super().get_route_handler()

        async def handle(request: Request) -> Response:
            if (
                request.method == "POST"
                and request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                != "application/json"
            ):
                raise HTTPException(400, "Request requires JSON")
            return await handler(request)

        return handle


class RequestBoundary:
    """Bound streamed bodies and contain private failures before Uvicorn logs them."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        path = scope["path"]
        limit = 1024 * 1024
        if path == "/api/images":
            limit = 11 * 1024 * 1024
        elif path.startswith("/api/results/"):
            limit = 65536
        elif path.startswith("/api/local-chat-pins"):
            limit = 8192
        elif path.startswith("/api/local-chat-reads"):
            limit = 786432 if path.endswith("/import") else 1024
        received = 0
        response_started = False

        async def bounded_receive() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    raise HTTPException(400, "Invalid request body size")
            return message

        async def private_send(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                headers = list(message.get("headers", []))
                if not any(key == b"cache-control" for key, _ in headers):
                    headers.append((b"cache-control", b"no-store"))
                headers.append((b"x-content-type-options", b"nosniff"))
                message["headers"] = headers
            await send(message)

        try:
            await self.app(scope, bounded_receive, private_send)
        except Exception as exc:
            logger.error("HTTP contract failed error_type=%s", type(exc).__name__)
            if not response_started:
                await JSONResponse(
                    {"ok": False, "error": "Chat send contract unavailable"}, status_code=500
                )(scope, receive, private_send)


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
            def digest() -> bytes:
                payload = json.dumps(
                    local.jobs.scheduled_jobs(),
                    sort_keys=True,
                    separators=(",", ":"),
                    ensure_ascii=False,
                )
                return hashlib.blake2b(payload.encode(), digest_size=16).digest()

            def event(topic: str) -> ServerSentEvent:
                return ServerSentEvent(event=topic, data="refresh", id=str(time.time_ns()))

            previous = local.live_events.snapshot()
            previous_jobs = await run_in_threadpool(digest)
            yield ServerSentEvent(retry=1500)
            yield event("sync")
            while True:
                await asyncio.sleep(0.75)
                current = local.live_events.snapshot()
                if current.jobs != previous.jobs:
                    current_jobs = await run_in_threadpool(digest)
                    if current_jobs != previous_jobs:
                        yield event("jobs")
                    previous_jobs = current_jobs
                if current.chats != previous.chats:
                    yield event("chats")
                previous = current

        return EventSourceResponse(
            stream(),
            ping=15,
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

    @app.head("/api/chats/requests/{request_id}", include_in_schema=False)
    @app.get("/api/chats/requests/{request_id}")
    def receipt(request_id: RequestId) -> dict[str, object]:
        record = local.queue.get("manual-" + request_id)
        if record is None or record["client_id"] not in (
            "manual:" + request_id,
            "manual:once:" + request_id,
        ):
            raise HTTPException(404, "Queue request not found")
        return {"send_id": record["send_id"], "status": record["status"]}

    @app.post("/api/chats", status_code=202)
    def fresh_chat(payload: FreshChatRequest) -> dict[str, object]:
        refs = image_refs(payload.images)
        for ref in refs:
            local.images.path(ref)
        accepted = local.queue.enqueue_manual(
            payload.prompt.strip(),
            images=refs,
            request_id=payload.request_id,
            pin_local_default=True,
        )
        return {"ok": True, "send_id": accepted["send_id"], "status": accepted["status"]}

    @app.post("/api/images")
    def upload(payload: ImageUpload) -> dict[str, object]:
        ref = local.images.save(payload.name, payload.data)
        return {
            "ok": True,
            "image": {"ref": ref, "name": ref.split("/", 1)[1], "url": "./api/images/" + ref},
        }

    @app.head("/api/images/{ref:path}", include_in_schema=False)
    @app.get("/api/images/{ref:path}")
    def image(ref: str) -> Response:
        try:
            mime, body = local.images.read(ref)
        except ValueError as exc:
            raise HTTPException(404) from exc
        return Response(body, media_type=mime)

    @app.head("/api/results", include_in_schema=False)
    @app.get("/api/results")
    def results(request: Request, params: Annotated[ResultsQuery, Query()]) -> dict[str, object]:
        if any(len(request.query_params.getlist(key)) != 1 for key in request.query_params):
            raise ValueError("Invalid result query")
        page = local.results.page(
            limit=params.limit, offset=params.offset, query=params.q.strip(), status=params.status
        )
        local.replies.annotate_response_markers(page["items"])
        local.results.annotate_local_reads(page["items"])
        return dict(page)

    @app.head("/api/results/{send_id}/turns", include_in_schema=False)
    @app.get("/api/results/{send_id}/turns")
    def turns(send_id: str) -> dict[str, object]:
        items = local.replies.turns(send_id)
        if items is None:
            raise HTTPException(404, "Run not found")
        return {"turns": items}

    @app.head("/api/results/{send_id}", include_in_schema=False)
    @app.get("/api/results/{send_id}")
    def detail(send_id: str) -> dict[str, object]:
        record = local.results.detail(send_id)
        if record is None:
            raise HTTPException(404, "Run not found")
        local.replies.annotate_response_markers([record])
        local.results.annotate_local_reads([record])
        queued = local.queue.get(send_id)
        record["images"] = (
            [
                {"name": ref.split("/", 1)[1], "url": "./api/images/" + ref}
                for ref in image_refs(queued["images"])
            ]
            if queued is not None
            else []
        )
        return record

    @app.post("/api/results/{send_id}/reply-recover")
    def recover(send_id: str, payload: EmptyRequest) -> dict[str, object]:
        return {"ok": True, **local.reply_dispatch.recover(send_id)}

    @app.post("/api/results/{send_id}/reply-queue", status_code=202)
    def followup(send_id: str, payload: FollowupRequest) -> dict[str, object]:
        return {
            "ok": True,
            "turn": local.replies.queue_followup(send_id, payload.reply_id, payload.text),
        }

    @app.post("/api/results/{send_id}/reply-intents", status_code=202)
    def prepare_reply(send_id: str, payload: ReplyRequest) -> dict[str, object]:
        turn = local.replies.prepare(
            send_id,
            ReplyIntent(payload.reply_id, payload.conversation_id, payload.parent_id, payload.text),
        )
        return {"ok": True, "dispatched": False, "turn": turn}

    @app.post("/api/results/{send_id}/reply-send", status_code=202)
    def send_reply(send_id: str, payload: ReplyRequest) -> dict[str, object]:
        turn = local.replies.queue_explicit_send(
            send_id,
            ReplyIntent(payload.reply_id, payload.conversation_id, payload.parent_id, payload.text),
        )
        return {
            "ok": True,
            "dispatched": False,
            "queued_for_explicit_dispatch": turn["status"] == "prepared",
            "turn": turn,
        }

    @app.head("/api/local-chat-pins", include_in_schema=False)
    @app.get("/api/local-chat-pins")
    def pins() -> dict[str, object]:
        items = local.results.local_pinned_runs()
        local.replies.annotate_response_markers(items)
        local.results.annotate_local_reads(items)
        return {"items": items}

    @app.post("/api/local-chat-pins")
    def pin(payload: PinRequest) -> dict[str, object]:
        if not local.results.set_local_pin(payload.send_id, pinned=payload.pinned):
            raise HTTPException(404, "Local run not found")
        return {"ok": True}

    @app.post("/api/local-chat-pins/import")
    def import_pins(payload: PinImport) -> dict[str, object]:
        local.results.import_legacy_local_pins(payload.send_ids)
        return {"ok": True}

    @app.post("/api/local-chat-reads")
    def read(payload: ReadRequest) -> dict[str, object]:
        record = local.results.detail(payload.send_id)
        if record is None:
            raise HTTPException(404, "Local run not found")
        local.replies.annotate_response_markers([record])
        if not payload.revision or record["last_reply_revision"] != payload.revision:
            raise ReplyConflict("Reply revision changed")
        local.results.mark_local_read(payload.send_id, payload.revision)
        return {"ok": True}

    @app.post("/api/local-chat-reads/import")
    def import_reads(payload: ReadImport) -> dict[str, object]:
        local.results.import_legacy_local_reads(payload.reads)
        return {"ok": True}

    @app.post("/api/local-chat-reads/all")
    def read_all(payload: EmptyRequest) -> dict[str, object]:
        return {"ok": True, "count": local.replies.mark_all_local_read()}

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
    )


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
