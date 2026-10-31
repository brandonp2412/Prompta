from __future__ import annotations

import logging
from collections.abc import Callable, Coroutine

from fastapi import HTTPException, Request
from fastapi.responses import JSONResponse, Response
from fastapi.routing import APIRoute
from starlette.types import ASGIApp, Message, Receive, Scope, Send

logger = logging.getLogger(__name__)


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
