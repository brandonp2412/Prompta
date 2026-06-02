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


# JS templates — stored as constants to avoid quoting issues
# Uses single quotes in JS, avoids needing escaped double quotes
_POLL_RESPONSE_JS = r"""
(function() {
    var msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
    if (msgs.length === 0) return JSON.stringify({text:'', done:false, thinking:true});
    var last = msgs[msgs.length - 1];
    var markdownEl = last.querySelector('.markdown');
    var text = markdownEl ? (markdownEl.textContent || '') : '';
    var isThinking = !markdownEl && !text;
    var stopBtn = document.querySelector('button[aria-label="Stop"]');
    var done = !stopBtn && !isThinking;
    var fullText = text || last.textContent || '';
    return JSON.stringify({text: fullText, done: done, thinking: isThinking});
})()
""".strip()

_FINAL_TEXT_JS = r"""
(function() {
    var msgs = document.querySelectorAll('[data-message-author-role="assistant"]');
    if (msgs.length === 0) return '';
    var last = msgs[msgs.length - 1];
    var md = last.querySelector('.markdown');
    return md ? md.textContent : last.textContent;
})()
""".strip()

_ASSISTANT_COUNT_JS = "document.querySelectorAll('[data-message-author-role=\"assistant\"]').length"


class CDPDriver:
    """Chrome DevTools Protocol driver for ChatGPT."""

    def __init__(self, cdp_port: int):
        self.port = cdp_port
        self.ws = None
        self._msg_id = 0
        self._access_token = ""
        self._conversation_url: Optional[str] = None
        self._lock = asyncio.Lock()

    # ── Connection ────────────────────────────────────────────

    async def connect(self):
        """Connect to Chrome's CDP on the ChatGPT page."""
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}/json/list")
        with urllib.request.urlopen(req) as resp:
            targets = json.loads(resp.read())

        chatgpt = [t for t in targets if t.get("type") == "page" and "chatgpt.com" in t.get("url", "")]
        if not chatgpt:
            pages = [t for t in targets if t.get("type") == "page"]
            if not pages:
                raise RuntimeError("No browser pages found. Open chatgpt.com first.")
            chatgpt = pages

        target = chatgpt[0]
        ws_url = target["webSocketDebuggerUrl"]
        logger.info("CDP connected to: %s", target.get("title", "")[:60])

        self.ws = await websockets.connect(ws_url, max_size=100 * 1024 * 1024)
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
        target_id = self._msg_id
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            raw = await asyncio.wait_for(self.ws.recv(), timeout=max(1, deadline - time.monotonic()))
            resp = json.loads(raw)
            if resp.get("id") == target_id:
                return resp
        raise TimeoutError(f"CDP timeout for {method}")

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
        await asyncio.sleep(2)

        # Wait for textarea AND send button to be ready
        for i in range(30):
            result = await self._js(
                "(function() {"
                "  var ta = document.querySelector('#prompt-textarea');"
                "  var btn = document.querySelector('button[data-testid=\"send-button\"]');"
                "  return JSON.stringify({hasTA: !!ta, hasBtn: !!btn, url: location.href});"
                "})()"
            )
            try:
                state = json.loads(result)
                if state.get("hasTA") and state.get("hasBtn"):
                    logger.info("Page ready: %s", state.get("url", ""))
                    break
            except (json.JSONDecodeError, TypeError):
                pass
            await asyncio.sleep(0.5)
        else:
            logger.warning("Page may not be fully ready")

        # Settle time for sentinel initialization
        await asyncio.sleep(2)
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
            # Focus the textarea
            await self._js(
                "(function() {"
                "  var el = document.querySelector('#prompt-textarea');"
                "  if (!el) return 'no textarea';"
                "  el.focus();"
                "  return 'focused';"
                "})()"
            )

            # Type the message via CDP Input.insertText
            await self._cdp("Input.insertText", {"text": text})
            await asyncio.sleep(0.5)

            # Verify text was inserted
            content = await self._js(
                "document.querySelector('#prompt-textarea').textContent || ''"
            )
            if not content:
                raise RuntimeError("Failed to insert text into textarea")

            logger.info("Typed message: %s", text[:60])

            # Wait for send button to be enabled (appears when textarea has content)
            for _ in range(10):
                has_btn = await self._js(
                    "(function() {"
                    "  var btn = document.querySelector('button[data-testid=\"send-button\"]');"
                    "  return btn && !btn.disabled ? 'yes' : 'no';"
                    "})()"
                )
                if has_btn == "yes":
                    break
                await asyncio.sleep(0.3)

            # Click send button via JS MouseEvent sequence
            result = await self._js(
                "(function() {"
                "  var btn = document.querySelector('button[data-testid=\"send-button\"]');"
                "  if (!btn) return 'no send button';"
                "  if (btn.disabled) return 'button disabled';"
                "  var events = ['pointerdown','mousedown','pointerup','mouseup','click'];"
                "  for (var i = 0; i < events.length; i++) {"
                "    btn.dispatchEvent(new MouseEvent(events[i], {bubbles:true, cancelable:true, view:window}));"
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

        conv_id = ""
        if "/c/" in url:
            conv_id = url.split("/c/")[1].split("/")[0].split("?")[0]

        return MessageResponse(
            conversation_id=conv_id,
            message_id=str(uuid.uuid4()),
            text="".join(c.delta for c in chunks),
            model="gpt-5-5-thinking",
            finish_reason=chunks[-1].finish_reason if chunks else "stop",
        )

    async def stream_response(self, timeout: float = 120) -> AsyncIterator[StreamChunk]:
        """Stream response chunks by polling the DOM.

        Strategy: The thinking model renders differently — the DOM may not show text
        until the full thinking+reasoning+text sequence completes. So we use a hybrid:
        1. Poll DOM for streaming text (when available)
        2. Fall back to polling the conversation API
        """
        initial_raw = await self._js(_ASSISTANT_COUNT_JS)
        initial_count = int(initial_raw) if initial_raw else 0

        # Wait for a new assistant message to appear (up to 60s)
        deadline = time.monotonic() + min(timeout, 60)
        while time.monotonic() < deadline:
            raw = await self._js(_ASSISTANT_COUNT_JS)
            count = int(raw) if raw else 0
            if count > initial_count:
                break
            await asyncio.sleep(0.5)
        else:
            raise RuntimeError("Timed out waiting for assistant response to appear")

        # Now we need to wait for the response to fully complete.
        # The thinking model has multiple phases: thinking → reasoning → text.
        # DOM polling may show empty during thinking phase.
        # We'll poll the Stop button to know when generation is done,
        # then fetch the final text from the conversation API.

        logger.info("Waiting for generation to complete...")
        generation_done = False
        deadline = time.monotonic() + timeout

        # First, try DOM-based streaming while the Stop button exists
        last_dom_text = ""
        while time.monotonic() < deadline:
            result = await self._js(_POLL_RESPONSE_JS)
            try:
                data = json.loads(result)
            except (json.JSONDecodeError, TypeError):
                await asyncio.sleep(0.5)
                continue

            current_text = data.get("text", "")
            is_done = data.get("done", False)
            is_thinking = data.get("thinking", False)

            # Yield deltas from DOM if we have text
            if not is_thinking and len(current_text) > len(last_dom_text):
                delta = current_text[len(last_dom_text):]
                last_dom_text = current_text
                yield StreamChunk(delta=delta)

            if is_done and not is_thinking:
                generation_done = True
                break

            await asyncio.sleep(0.5)

        if not generation_done:
            logger.warning("Timed out waiting for generation to complete")

        # Wait for URL to change to /c/{conversation_id}
        url = ""
        for _ in range(30):  # Wait up to 15s for URL change
            url = await self._js("window.location.href")
            if "/c/" in url:
                break
            await asyncio.sleep(0.5)
        self._conversation_url = url

        if "/c/" in url:
            conv_id = url.split("/c/")[1].split("/")[0].split("?")[0]
            logger.info("Conversation ID: %s", conv_id)

            # Wait for the response to be available in the API
            # Retry up to 30s
            for attempt in range(60):
                final_text = await self._fetch_assistant_text(conv_id)
                if final_text:
                    break
                await asyncio.sleep(0.5)
            else:
                final_text = ""

            if final_text and len(final_text) > len(last_dom_text):
                delta = final_text[len(last_dom_text):]
                yield StreamChunk(delta=delta)
        else:
            logger.warning("URL did not change to /c/ pattern: %s", url)

        yield StreamChunk(delta="", finish_reason="stop")

    async def _fetch_assistant_text(self, conversation_id: str) -> str:
        """Fetch the assistant's final text response from the conversation API."""
        token = self._access_token
        js_code = (
            "(async function() {"
            "  try {"
            "    var r = await fetch('/backend-api/conversation/' + '" + conversation_id + "' + '?offset=0&limit=5', {"
            "      headers: {'Authorization': 'Bearer ' + '" + token + "'}"
            "    });"
            "    if (!r.ok) return 'FETCH_ERROR:' + r.status;"
            "    var conv = await r.json();"
            "    var mapping = conv.mapping || {};"
            "    var lastText = '';"
            "    for (var id in mapping) {"
            "      var node = mapping[id];"
            "      if (node.message && node.message.author && node.message.author.role === 'assistant') {"
            "        var ct = node.message.content.content_type;"
            "        if (ct === 'text') {"
            "          var parts = node.message.content.parts || [];"
            "          if (parts.length > 0 && parts[0]) lastText = parts[0];"
            "        }"
            "      }"
            "    }"
            "    return lastText;"
            "  } catch(e) { return 'ERROR:' + e.message; }"
            "})()"
        )
        result = await self._js(js_code, timeout=15)
        logger.debug("_fetch_assistant_text result: %s", (result or "")[:200])
        return result or ""

    # ── API helpers ───────────────────────────────────────────

    async def get_models(self) -> list[dict]:
        """Get the model catalog."""
        token = self._access_token
        raw = await self._js(
            "(async () => {"
            "  var r = await fetch('/backend-api/models?iim=false&is_gizmo=false', {"
            "    headers: {'Authorization': 'Bearer " + token + "'}"
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
        token = self._access_token
        raw = await self._js(
            "(async () => {"
            "  var r = await fetch('/backend-api/gizmos/snorlax/sidebar?owned_only=true&conversations_per_gizmo=5&limit=50', {"
            "    headers: {'Authorization': 'Bearer " + token + "'}"
            "  });"
            "  var data = await r.json();"
            "  var items = data.items || [];"
            "  return JSON.stringify(items.map(function(i) {"
            "    var g = (i.gizmo || {}).gizmo || {};"
            "    return {"
            "      id: g.id,"
            "      name: (g.display || {}).name || '',"
            "      memory_scope: g.memory_scope || '',"
            "      short_url: g.short_url || ''"
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
        token = self._access_token
        raw = await self._js(
            "(async () => {"
            "  var r = await fetch('/backend-api/conversation/" + conversation_id + "', {"
            "    headers: {'Authorization': 'Bearer " + token + "'}"
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
        return self.ws is not None and self.ws.state.name == "OPEN"
