"""Shared browser-independent helpers for Prompta browser automation."""

from __future__ import annotations

import json
from typing import Any

from .browser_script_loader import load_browser_script, render_browser_script
from .chatgpt_dom import (
    ASSISTANT_MESSAGE_SELECTOR,
    STOP_BUTTON_SELECTORS,
    STREAMING_SELECTOR,
    TURN_SELECTOR,
)
from .conversation_snapshot import CONVERSATION_SNAPSHOT_SCRIPT, parse_conversation_snapshot


class BrowsingContextUnavailableError(RuntimeError):
    """Raised when a tracked browser tab/context no longer exists."""


class BrowserDriverBase:
    # Shared browser-independent helpers used by the Playwright driver.

    def __init__(self, url: str = "") -> None:
        self.url = url
        self.context = ""
        self._network_subscribed = False
        self._send_capture: dict[str, Any] | None = None
        self.needs_browser_restart = False

    async def arm_page_send_probe(self) -> None:
        await self.eval(load_browser_script("arm_page_send_probe.js"))

    async def page_send_probe(self) -> dict[str, Any]:
        raw = await self.eval(load_browser_script("page_send_probe.js"))
        return json.loads(raw or "{}")

    async def clear_page_send_probe(self) -> dict[str, Any]:
        raw = await self.eval(load_browser_script("clear_page_send_probe.js"))
        return json.loads(raw or "{}")

    @staticmethod
    def captured_send_response(capture: dict[str, Any]) -> tuple[str, int] | None:
        request_id = str(capture.get("request_id") or "")
        status = int(capture.get("status") or 0)
        if request_id and bool(capture.get("response_started")) and 200 <= status < 400:
            return request_id, status
        return None

    def clear_send_capture(self, capture: dict[str, Any]) -> None:
        if self._send_capture is capture:
            self._send_capture = None

    async def eval(
        self,
        expression: str,
        *,
        await_promise: bool = False,
        context: str | None = None,
    ) -> Any:
        raise NotImplementedError

    async def ensure_token(self) -> str:
        raw = await self.eval(
            load_browser_script("ensure_token.js"),
            await_promise=True,
        )
        payload = json.loads(raw or "{}")
        token = str(payload.get("token") or "")
        if not payload.get("ok") or not token:
            raise RuntimeError("Prompta browser profile is not logged into ChatGPT")
        return token

    async def conversation_final_event(
        self,
        conversation_id: str,
        *,
        context: str | None = None,
    ) -> dict[str, Any]:
        script = render_browser_script(
            "conversation_final_event.js",
            CONVERSATION_ID=conversation_id,
        )
        raw = await self.eval(
            script,
            context=context,
            await_promise=True,
        )
        payload = json.loads(raw or "{}")
        return payload if isinstance(payload, dict) else {}

    async def conversation_activity(self, context: str) -> dict[str, Any]:
        script = render_browser_script(
            "conversation_activity.js",
            ASSISTANT_SELECTOR=ASSISTANT_MESSAGE_SELECTOR,
            TURN_SELECTOR=TURN_SELECTOR,
            STOP_SELECTOR=",".join(STOP_BUTTON_SELECTORS),
            STREAMING_SELECTOR=STREAMING_SELECTOR,
        )
        raw = await self.eval(script, context=context)
        return json.loads(raw or "{}")

    async def conversation_snapshot(self, context: str) -> dict[str, Any]:
        raw = await self.eval(CONVERSATION_SNAPSHOT_SCRIPT, context=context)
        return parse_conversation_snapshot(raw)


# Compatibility alias for older imports; there is no WebDriver transport.
WebDriverBase = BrowserDriverBase
