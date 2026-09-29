"""Shared browser-independent helpers for Prompta fresh-chat delivery."""

from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlsplit

from .browser_script_loader import load_browser_script


class BrowsingContextUnavailableError(RuntimeError):
    """Raised when a Prompta-owned browser tab no longer exists."""


_SEND_ENDPOINTS = ("/backend-api/f/conversation", "/backend-api/conversation")


class BrowserDriverBase:
    def __init__(self, url: str = "") -> None:
        self.url = url
        self.context = ""
        self._network_subscribed = False
        self._send_capture: dict[str, Any] | None = None
        self.needs_browser_restart = False

    @staticmethod
    def _is_send_endpoint(url: str) -> bool:
        return urlsplit(url).path.rstrip("/") in _SEND_ENDPOINTS

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
        raw = await self.eval(load_browser_script("ensure_token.js"), await_promise=True)
        payload = json.loads(raw or "{}")
        token = str(payload.get("token") or "")
        if not payload.get("ok") or not token:
            raise RuntimeError("Prompta browser profile is not logged into ChatGPT")
        return token


WebDriverBase = BrowserDriverBase
