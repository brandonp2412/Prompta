"""OpenAI-compatible API server — CDP-driven.

Routes all requests through the Chrome browser via CDP.
The browser handles sentinel (Turnstile + PoW + so) automatically.

Endpoints:
  POST /v1/chat/completions  — chat with streaming support
  GET  /v1/models            — model catalog
  GET  /v1/projects          — ChatGPT projects
  GET  /health               — health check
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Optional

from aiohttp import web

from .cdp_driver import CDPDriver

logger = logging.getLogger(__name__)

# Model mapping: OpenAI-style names → ChatGPT web slugs
MODEL_MAP = {
    "gpt-5.5": "gpt-5-5",
    "gpt-5.5-thinking": "gpt-5-5-thinking",
    "gpt-5.3": "gpt-5-3",
    "gpt-5.2": "gpt-5-2",
    "gpt-5.1": "gpt-5-1",
    "gpt-5": "gpt-5",
    "gpt-5-mini": "gpt-5-mini",
    "gpt-5.3-mini": "gpt-5-3-mini",
    "auto": "auto",
    # Aliases
    "gpt-4o": "auto",
    "gpt-4": "gpt-5",
    "gpt-3.5-turbo": "gpt-5-mini",
}

# Reverse map for responses
REVERSE_MODEL_MAP = {v: k for k, v in MODEL_MAP.items()}


class APIServer:
    """OpenAI-compatible API server backed by CDP driver."""

    def __init__(self, driver: CDPDriver, host: str = "0.0.0.0", port: int = 8080):
        self.driver = driver
        self.host = host
        self.port = port
        self.app = web.Application(client_max_size=10 * 1024 * 1024)
        self._setup_routes()
        self._request_lock = asyncio.Lock()
        self._request_count = 0

    def _setup_routes(self):
        self.app.router.add_post("/v1/chat/completions", self.handle_chat)
        self.app.router.add_post("/chat/completions", self.handle_chat)
        self.app.router.add_get("/v1/models", self.handle_models)
        self.app.router.add_get("/v1/projects", self.handle_projects)
        self.app.router.add_get("/health", self.handle_health)
        self.app.router.add_get("/", self.handle_health)

    async def handle_health(self, request: web.Request) -> web.Response:
        connected = self.driver.is_connected
        return web.json_response({
            "status": "ok" if connected else "disconnected",
            "cdp_connected": connected,
            "requests_served": self._request_count,
        })

    async def handle_models(self, request: web.Request) -> web.Response:
        """GET /v1/models — return model catalog."""
        try:
            models_raw = await self.driver.get_models()
        except Exception:
            models_raw = []

        # Build OpenAI-compatible model list
        models = []
        for m in models_raw:
            slug = m.get("slug", "")
            title = m.get("title", "")
            models.append({
                "id": slug,
                "object": "model",
                "created": 1700000000,
                "owned_by": "chatgpt-web",
                "permission": [],
                "root": slug,
                "parent": None,
            })

        # Add thinking variants
        thinking_models = []
        for m in models_raw:
            slug = m.get("slug", "")
            rt = m.get("reasoning_type", "")
            if rt == "auto":
                thinking_slug = f"{slug}-thinking"
                thinking_models.append({
                    "id": thinking_slug,
                    "object": "model",
                    "created": 1700000000,
                    "owned_by": "chatgpt-web",
                    "permission": [],
                    "root": slug,
                    "parent": slug,
                })
        models.extend(thinking_models)

        if not models:
            # Fallback
            for slug in ["auto", "gpt-5-5", "gpt-5-5-thinking", "gpt-5-mini"]:
                models.append({
                    "id": slug, "object": "model",
                    "created": 1700000000, "owned_by": "chatgpt-web",
                })

        return web.json_response({"object": "list", "data": models})

    async def handle_projects(self, request: web.Request) -> web.Response:
        """GET /v1/projects — return ChatGPT projects."""
        try:
            projects = await self.driver.get_projects()
        except Exception as e:
            logger.error("Failed to get projects: %s", e)
            projects = []

        return web.json_response({"object": "list", "data": projects})

    async def handle_chat(self, request: web.Request) -> web.Response:
        """POST /v1/chat/completions — chat completion (streaming + non-streaming)."""
        self._request_count += 1

        try:
            body = await request.json()
        except json.JSONDecodeError:
            return web.json_response({"error": {"message": "Invalid JSON", "type": "invalid_request_error"}},
                                     status=400)

        # Parse request
        messages = body.get("messages", [])
        model = body.get("model", "auto")
        stream = body.get("stream", False)
        project_id = body.get("project_id") or body.get("gizmo_id")
        # Also check metadata for project
        meta = body.get("metadata", {})
        if not project_id:
            project_id = meta.get("project_id") or meta.get("gizmo_id")

        if not messages:
            return web.json_response({"error": {"message": "No messages", "type": "invalid_request_error"}},
                                     status=400)

        # Get the last user message
        user_message = ""
        for msg in reversed(messages):
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Multimodal — extract text parts
                    parts = []
                    for part in content:
                        if isinstance(part, str):
                            parts.append(part)
                        elif isinstance(part, dict) and part.get("type") == "text":
                            parts.append(part.get("text", ""))
                    user_message = "\n".join(parts)
                else:
                    user_message = str(content)
                break

        if not user_message:
            return web.json_response({"error": {"message": "No user message", "type": "invalid_request_error"}},
                                     status=400)

        # Resolve model slug
        model_slug = MODEL_MAP.get(model, model)

        # Determine thinking mode
        use_thinking = "thinking" in model_slug or model_slug.endswith("-thinking")
        base_model = model_slug.replace("-thinking", "")

        logger.info("Request: model=%s, project=%s, stream=%s, msg=%s",
                    model, project_id, stream, user_message[:60])

        # Process request (serialized — one at a time)
        async with self._request_lock:
            try:
                # Navigate to appropriate context
                await self.driver.navigate_new_chat(gizmo_id=project_id)
                await asyncio.sleep(1)

                # Type and send
                await self.driver.send_message(user_message)

                if stream:
                    return await self._handle_stream(request, model_slug)
                else:
                    return await self._handle_non_stream(request, model_slug)

            except Exception as e:
                logger.error("Chat failed: %s", e, exc_info=True)
                return web.json_response({
                    "error": {"message": str(e), "type": "server_error"}
                }, status=500)

    async def _handle_non_stream(self, request: web.Request, model: str) -> web.Response:
        """Handle non-streaming chat completion."""
        response = await self.driver.wait_for_response(timeout=120)

        completion_id = f"chatcmpl-{uuid.uuid4().hex[:29]}"
        created = int(time.time())

        return web.json_response({
            "id": completion_id,
            "object": "chat.completion",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": response.text,
                },
                "finish_reason": response.finish_reason,
            }],
            "usage": {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0,
            },
        })

    async def _handle_stream(self, request: web.Request, model: str) -> web.Response:
        """Handle streaming chat completion via SSE."""
        completion_id = f"chatcmpl-{uuid.uuid4().hex[:29]}"
        created = int(time.time())

        response = web.StreamResponse()
        response.content_type = "text/event-stream"
        response.headers["Cache-Control"] = "no-cache"
        response.headers["Connection"] = "keep-alive"
        await response.prepare(request)

        # Send initial role chunk
        await self._send_sse(response, {
            "id": completion_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [{
                "index": 0,
                "delta": {"role": "assistant", "content": ""},
                "finish_reason": None,
            }],
        })

        # Stream response chunks
        try:
            async for chunk in self.driver.stream_response(timeout=120):
                if chunk.delta:
                    await self._send_sse(response, {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {"content": chunk.delta},
                            "finish_reason": None,
                        }],
                    })

                if chunk.finish_reason:
                    await self._send_sse(response, {
                        "id": completion_id,
                        "object": "chat.completion.chunk",
                        "created": created,
                        "model": model,
                        "choices": [{
                            "index": 0,
                            "delta": {},
                            "finish_reason": chunk.finish_reason,
                        }],
                    })

        except Exception as e:
            logger.error("Stream error: %s", e)
            await self._send_sse(response, {
                "id": completion_id,
                "object": "chat.completion.chunk",
                "created": created,
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {"content": f"\n\n[Error: {e}]"},
                    "finish_reason": "error",
                }],
            })

        # Send [DONE]
        await response.write(b"data: [DONE]\n\n")
        await response.write_eof()
        return response

    @staticmethod
    async def _send_sse(response: web.StreamResponse, data: dict):
        """Send an SSE event."""
        payload = f"data: {json.dumps(data)}\n\n"
        await response.write(payload.encode("utf-8"))

    async def run(self):
        """Start the server."""
        runner = web.AppRunner(self.app)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        logger.info("API server listening on http://%s:%d", self.host, self.port)
        logger.info("Endpoints:")
        logger.info("  POST /v1/chat/completions")
        logger.info("  GET  /v1/models")
        logger.info("  GET  /v1/projects")
        logger.info("  GET  /health")

        # Keep running
        try:
            while True:
                await asyncio.sleep(3600)
        except asyncio.CancelledError:
            pass
        finally:
            await runner.cleanup()
