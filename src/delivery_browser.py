from __future__ import annotations

import asyncio
import math
import os
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .browser_session import BrowserSession
from .cache import ActiveConversation, ChatCache
from .control_server import ControlDeferredError
from .conversation_actions import ConversationActions
from .playwright_driver import PlaywrightDriver
from .rate_limit import RateLimitError
from .scheduler_runtime import SchedulerRuntime
from .send_jobs import DeliveryBackendUnavailableError

_DEFAULT_SEND_TIMEOUT_SECONDS = 20.0
_DELIVERY_WINDOW_PREFIX = "prompta-delivery:"


class BrowserDeliverySender:
    """Own one durable delivery from SQLite lease through ChatGPT browser send."""

    def __init__(
        self,
        state_path: Path,
        *,
        cache_path: Path | None = None,
        profile: Path | None = None,
        chrome_path: str = "/usr/bin/chromium",
        debugger_address: str | None = None,
        flaresolverr_url: str | None = None,
        auth_timeout_seconds: float = 30.0,
        driver_factory: Callable[[], PlaywrightDriver] | None = None,
    ) -> None:
        self.state_path = state_path.expanduser()
        state_dir = self.state_path.parent
        self.cache_path = (cache_path or state_dir / "chats.sqlite3").expanduser()
        self.profile = (
            profile
            or Path(
                os.environ.get(
                    "PROMPTA_CHROME_PROFILE",
                    str(state_dir / "chrome-profile"),
                )
            )
        ).expanduser()
        self.chrome_path = chrome_path
        self.debugger_address = debugger_address
        self.flaresolverr_url = flaresolverr_url
        self.auth_timeout_seconds = max(0.1, float(auth_timeout_seconds))
        self.driver_factory = driver_factory
        self.runtime = SchedulerRuntime(self.state_path, self.state_path)

    def _new_driver(self) -> PlaywrightDriver:
        if self.driver_factory is not None:
            return self.driver_factory()
        return PlaywrightDriver(
            profile=self.profile,
            chrome_path=self.chrome_path,
            headless=True,
            auth_timeout_seconds=self.auth_timeout_seconds,
            debugger_address=self.debugger_address,
            flaresolverr_url=self.flaresolverr_url,
            ownership_prefix=_DELIVERY_WINDOW_PREFIX,
        )

    def _global_cooldown_remaining(self) -> float:
        return self.runtime.global_backoff_remaining()

    def _record_send_attempt(self) -> None:
        self.runtime.update_scheduler_state({"last_attempt_at": time.time()})

    def _defer_busy_reply(self, conversation_id: str) -> None:
        cache = ChatCache(self.cache_path)
        try:
            if cache.status(conversation_id) == "active":
                raise ControlDeferredError(
                    "Conversation is still active; reply was deferred before delivery"
                )
        finally:
            cache.close()

    def __call__(
        self,
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str],
    ) -> str:
        remaining = self._global_cooldown_remaining()
        if remaining > 0:
            raise RateLimitError(
                "ChatGPT account-wide rate limit backoff is active",
                retry_after=max(1, math.ceil(remaining)),
            )

        gap = self.runtime.send_gap_remaining(time.time())
        if gap > 0:
            raise ControlDeferredError(
                "Prompta global send gap is active",
                retry_after=max(0.1, gap),
            )

        if operation == "reply":
            self._defer_busy_reply(conversation_id)
        elif operation != "once":
            raise ValueError(f"unsupported Prompta delivery operation: {operation}")

        try:
            result = asyncio.run(
                self._send_browser(operation, message, conversation_id, attachments)
            )
        except RateLimitError as exc:
            delay = self.runtime.record_global_rate_limit(exc)
            raise RateLimitError(
                str(exc),
                retry_after=max(1, math.ceil(delay)),
            ) from exc

        return result

    async def _send_browser(
        self,
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str],
    ) -> str:
        active: dict[str, ActiveConversation] = {}
        cache = ChatCache(self.cache_path)
        browser = BrowserSession("https://chatgpt.com", self._new_driver)

        async def wait_for_cached_response(
            _conversation_id: str,
            **_kwargs: Any,
        ) -> bool:
            return False

        async def enrich_completed_tool_calls(
            _conversation_id: str,
            _snapshot: dict[str, Any],
            **_kwargs: Any,
        ) -> None:
            return None

        send_attempted = False

        def record_send_attempt() -> None:
            nonlocal send_attempted
            self._record_send_attempt()
            send_attempted = True

        actions = ConversationActions(
            cache,
            active,
            _DEFAULT_SEND_TIMEOUT_SECONDS,
            ensure_driver=browser.ensure_driver,
            ensure_high_effort=browser.ensure_high_effort,
            ensure_route=browser.ensure_conversation_route,
            enrich_completed_tool_calls=enrich_completed_tool_calls,
            wait_for_cached_response=wait_for_cached_response,
            unattended_mode=self.runtime.unattended_mode,
            before_send_attempt=record_send_attempt,
        )
        try:
            try:
                if operation == "once":
                    return await actions.send_once(
                        message,
                        attachments=attachments,
                    )
                return await actions.send_reply(
                    conversation_id,
                    message,
                    attachments=attachments,
                )
            except (RateLimitError, ControlDeferredError):
                raise
            except Exception as exc:
                if not send_attempted:
                    raise DeliveryBackendUnavailableError(str(exc)) from exc
                raise
        finally:
            for context, tracked in list(active.items()):
                cache.release_browser_context(
                    tracked.conversation_id,
                    context_id=context,
                )
            active.clear()
            driver = browser.driver
            if driver is not None:
                await driver.close()
            cache.close()
