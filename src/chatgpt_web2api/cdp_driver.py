"""CDP Driver — browser automation via Chrome DevTools Protocol.

All HTTP to chatgpt.com routes through the browser. No sentinel solving
needed — the browser handles Turnstile/PoW/so challenges automatically.

Operations:
  - Connect to Chrome CDP
  - Get auth token
  - Navigate to new chat or project
  - Type message via Input.insertText
  - Click send via JS MouseEvent sequence
  - Stream response by polling DOM
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
import urllib.request
import uuid
from dataclasses import dataclass, field
from typing import AsyncIterator, Optional

try:
    import websockets
except ImportError:
    raise ImportError("pip install websockets")

logger = logging.getLogger(__name__)


@dataclass
class MessageResponse:
    """Response from a chat message."""
    conversation_id: str
    message_id: str
    text: str
    model: str
    finish_reason: str = "stop"
    thinking: str = ""
    reasoning_recap: str = ""


@dataclass
class StreamChunk:
    """A streaming chunk."""
    delta: str
    finish_reason: Optional[str] = None
    thinking_delta: str = ""


class CDPDriver:
    """Chrome DevTools Protocol driver for ChatGPT."""

    def __init__(self, cdp_port: int):
        self.port = cdp_port
        self.ws = None
        self._msg_id = 0
        self._access_token = ""
        self._conversation_url: Optional[str] = None
        self._lock = asyncio.Lock()
        self._page_title = ""

    # ── Connection ────────────────────────────────────────────

    async def connect(self):
        """Connect to Chrome's CDP on the ChatGPT page."""
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/list")
        with urllib.request.urlopen(req) as resp:
            targets = json.loads(resp.read())

        # Prefer ChatGPT page
        chatgpt = [t for t in targets if t.get("type") == "page" and "chatgpt.com" in t.get("url", "")]
        if not chatgpt:
            # Fall back to any page
            pages = [t for t in targets if t.get("type") == "page"]
            if not pages:
                raise RuntimeError("No browser pages found. Open chatgpt.com first.")
            chatgpt = pages

        target = chatgpt[0]
        ws_url = target["webSocketDebuggerUrl"]
        self._page_title = target.get("title", "")
        logger.info("CDP connected to: %s", self._page_title[:60])

        self.ws = await websockets.connect(ws_url, max_size=100 * 1024 * 1024)

        # Get auth token
        await self._refresh_token()

    async def _refresh_token(self):
        """Get a fresh access token from /api/auth/session."""
        raw = await self._js(
            "(async () => {"
            "  const r = await fetch('/api/auth/session', {credentials:'include'});"
            "  const d = await r.json();"
            "  return JSON.stringify({token: d.accessToken || '', user: d.user?.name || ''});"
            "})()"
        )
        data = json.loads(raw)
        self._access_token = data.get("token", "")
        if not self._access_token:
            raise RuntimeError("No access token — are you logged into ChatGPT?")
        logger.info("Auth token: %d chars, user: %s", len(self._access_token), data.get("user", ""))

    # ── CDP primitives ────────────────────────────────────────

    async def _cdp(self, method: str, params: dict = None, timeout: float = 15) -> dict:
        """Send a CDP command and wait for response."""
        self._msg_id += 1
        msg = {"id": self._msg_id, "method": method, "params": params or {}}
        await self.ws.send(json.dumps(msg))
        while True:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=timeout)
            resp = json.loads(raw)
            if resp.get("id") == self._msg_id:
                return resp

    async def _js(self, expr: str, timeout: float = 15) -> str:
        """Evaluate JS and return string value."""
        resp = await self._cdp("Runtime.evaluate", {
            "expression": expr,
            "awaitPromise": True,
            "returnByValue": True,
            "timeout": int(timeout * 1000),
        }, timeout=timeout)
        return resp.get("result", {}).get("result", {}).get("value", "")

    # ── Navigation ────────────────────────────────────────────

    async def navigate_new_chat(self, gizmo_id: str = None):
        """Navigate to a new chat, optionally within a project."""
        if gizmo_id:
            url = f"https://chatgpt.com/g/{gizmo_id}/project"
        else:
            url = "https://chatgpt.com/"

        logger.info("Navigating to: %s", url)
        await self._cdp("Page.navigate", {"url": url})
        await asyncio.sleep(4)  # Wait for page load

        # Wait for the prompt textarea to appear
        for _ in range(20):
            has = await self._js("!!document.querySelector('#prompt-textarea')")
            if has:
                break
            await asyncio.sleep(0.5)

        self._conversation_url = None

    async def navigate_conversation(self, conversation_id: str):
        """Navigate to an existing conversation."""
        url = f"https://chatgpt.com/c/{conversation_id}"
        logger.info("Navigating to: %s", url)
        await self._cdp("Page.navigate", {"url": url})
        await asyncio.sleep(4)
        self._conversation_url = url

    # ── Message operations ────────────────────────────────────

    async def send_message(self, text: str) -> None:
        """Type a message and click send."""
        async with self._lock:
            # Focus the textarea and clear any existing content
            await self._js(
                "(async () => {"
                "  const el = document.querySelector('#prompt-textarea');"
                "  if (!el) return 'no textarea';"
                "  el.focus();"
                "  el.textContent = '';"
                "  el.innerText = '';"
                "  return 'cleared';"
                "})()"
            )

            # Type the message via CDP Input.insertText
            await self._cdp("Input.insertText", {"text": text})
            await asyncio.sleep(0.5)

            # Verify text was inserted
            content = await self._js("document.querySelector('#prompt-textarea').textContent || ''")
            if not content:
                raise RuntimeError("Failed to insert text into textarea")

            logger.info("Typed message: %s", text[:60])

            # Click send button via JS MouseEvent sequence (proven to work)
            result = await self._js(
                "(async () => {"
                "  const btn = document.querySelector('button[data-testid=\"send-button\"]');"
                "  if (!btn) return 'no send button';"
                "  const events = ['pointerdown','mousedown','pointerup','mouseup','click'];"
                "  for (const t of events) {"
                "    btn.dispatchEvent(new MouseEvent(t, {bubbles:true, cancelable:true, view:window}));"
                "  }"
                "  return 'sent';"
                "})()"
            )
            logger.info("Send result: %s", result)

            if result != "sent":
                raise RuntimeError(f"Send failed: {result}")

    async def wait_for_response(self, timeout: float = 120) -> MessageResponse:
        """Wait for a complete response (non-streaming)."""
        chunks = []
        async for chunk in self.stream_response(timeout=timeout):
            chunks.append(chunk)

        if not chunks:
            raise RuntimeError("No response received")

        # Get conversation URL
        url = await self._js("window.location.href")
        self._conversation_url = url

        # Extract conversation ID from URL
        conv_id = ""
        if "/c/" in url:
            conv_id = url.split("/c/")[1].split("/")[0].split("?")[0]

        return MessageResponse(
            conversation_id=conv_id,
            message_id=str(uuid.uuid4()),
            text="".join(c.delta for c in chunks),
            model=chunks[-1].model if hasattr(chunks[-1], "model") else "gpt-5-5-thinking",
            finish_reason=chunks[-1].finish_reason if chunks else "stop",
        )

    async def stream_response(self, timeout: float = 120) -> AsyncIterator[StreamChunk]:
        """Stream response chunks by polling the DOM."""
        # Count assistant messages before we start
        initial_count = int(await self._js(
            "document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"
        ) or "0")

        # Wait for a new assistant message to appear
        deadline = time.monotonic() + min(timeout, 15)
        while time.monotonic() < deadline:
            count = int(await self._js(
                "document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"
            ) or "0")
            if count > initial_count:
                break
            await asyncio.sleep(0.3)
        else:
            raise RuntimeError("Timed out waiting for assistant response")

        # Now poll the last assistant message for text changes
        last_text = ""
        idle_count = 0
        max_idle = 15  # 3 seconds of no change = done
        deadline = time.monotonic() + timeout

        while time.monotonic() < deadline:
            # Get the text of the last assistant message's markdown content
            result = await self._js(
                "(function() {"
                "  const msgs = document.querySelectorAll('[data-message-author-role=\"assistant\"]');"
                "  if (msgs.length === 0) return JSON.stringify({text:'', done:false, thinking:''});"
                "  const last = msgs[msgs.length - 1];"
                "  "
                "  // Try to get the main text content (skip thinking blocks)"
                "  const markdownEl = last.querySelector('.markdown');"
                "  const text = markdownEl ? markdownEl.textContent : last.textContent || '';"
                "  "
                "  // Check if generation is done (no Stop button)"
                "  const stopBtn = document.querySelector('button[aria-label=\"Stop\"]');"
                "  const done = !stopBtn;"
                "  "
                "  return JSON.stringify({text: text, done: done});"
                "})()"
            )

            try:
                data = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                await asyncio.sleep(0.2)
                continue

            current_text = data.get("text", "")
            is_done = data.get("done", False)

            # Yield only the delta
            if len(current_text) > len(last_text):
                delta = current_text[len(last_text):]
                last_text = current_text
                idle_count = 0
                yield StreamChunk(delta=delta)
            else:
                idle_count += 1

            if is_done and idle_count > 2:
                # Response complete
                yield StreamChunk(delta="", finish_reason="stop")
                break

            if idle_count > max_idle and not is_done:
                # No change for 3+ seconds while not done — might be stuck
                # Check one more time
                await asyncio.sleep(1)

            await asyncio.sleep(0.2)

    # ── API helpers ───────────────────────────────────────────

    async def get_models(self) -> list[dict]:
        """Get the model catalog."""
        raw = await self._js(
            "(async () => {"
            "  const r = await fetch('/backend-api/models?iim=false&is_gizmo=false', {"
            "    headers: {'Authorization': 'Bearer " + self._access_token + "'}"
            "  });"
            "  return await r.text();"
            "})()"
        )
        try:
            data = json.loads(raw)
            return data.get("models", [])
        except json.JSONDecodeError:
            return []

    async def get_projects(self) -> list[dict]:
        """Get the project/gizmo list."""
        raw = await self._js(
            "(async () => {"
            "  const r = await fetch('/backend-api/gizmos/snorlax/sidebar?owned_only=true&conversations_per_gizmo=5&limit=50', {"
            "    headers: {'Authorization': 'Bearer " + self._access_token + "'}"
            "  });"
            "  const data = await r.json();"
            "  const items = data.items || [];"
            "  return JSON.stringify(items.map(i => {"
            "    const g = (i.gizmo || {}).gizmo || {};"
            "    return {"
            "      id: g.id,"
            "      name: (g.display || {}).name || '',"
            "      memory_scope: g.memory_scope || '',"
            "      short_url: g.short_url || '',"
            "    };"
            "  }));"
            "})()"
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return []

    async def get_conversation(self, conversation_id: str) -> dict:
        """Get conversation details."""
        raw = await self._js(
            "(async () => {"
            "  const r = await fetch('/backend-api/conversation/" + conversation_id + "', {"
            "    headers: {'Authorization': 'Bearer " + self._access_token + "'}"
            "  });"
            "  return await r.text();"
            "})()"
        )
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}

    # ── Lifecycle ─────────────────────────────────────────────

    async def close(self):
        if self.ws:
            await self.ws.close()
            self.ws = None
        logger.info("CDP driver closed")

    @property
    def is_connected(self) -> bool:
        return self.ws is not None and not self.ws.closed
