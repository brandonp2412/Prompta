from __future__ import annotations

import argparse
import asyncio
import logging
import os
from contextlib import suppress
from pathlib import Path

from .browser_session import BrowserSession, DriverFactory
from .cache import ChatCache
from .conversation_tracker import ConversationTracker
from .persistence import DEFAULT_RUNTIME_PATH
from .playwright_driver import PlaywrightDriver
from .scheduler_runtime import SchedulerRuntime
from .service_health import ServiceHealthStore, notify_watchdog

logger = logging.getLogger(__name__)

_CONVERSATION_WINDOW_PREFIX = "prompta-conversation:"
_DEFAULT_RECOVERY_MESSAGE_TIMEOUT_SECONDS = 12.0
_DEFAULT_POLL_SECONDS = 1.0
_WATCHDOG_HEARTBEAT_SECONDS = 30.0


class ConversationWorker:
    """Own durable active-conversation recovery, polling, and final cache capture."""

    def __init__(
        self,
        state_path: Path = DEFAULT_RUNTIME_PATH,
        *,
        cache_path: Path | None = None,
        chrome_profile: Path | None = None,
        chrome_path: str = "/usr/bin/chromium",
        chrome_debugger_address: str | None = None,
        flaresolverr_url: str | None = None,
        chrome_auth_timeout_seconds: float = 30.0,
        driver_factory: DriverFactory | None = None,
        recovery_message_timeout_seconds: float = _DEFAULT_RECOVERY_MESSAGE_TIMEOUT_SECONDS,
    ) -> None:
        self.state_path = state_path.expanduser()
        state_dir = self.state_path.parent
        self.cache_path = (cache_path or state_dir / "chats.sqlite3").expanduser()
        self.profile = (
            chrome_profile
            or Path(
                os.environ.get(
                    "PROMPTA_CHROME_PROFILE",
                    str(state_dir / "chrome-profile"),
                )
            )
        ).expanduser()
        self.chrome_path = chrome_path
        self.debugger_address = chrome_debugger_address
        self.flaresolverr_url = flaresolverr_url
        self.auth_timeout_seconds = max(0.1, float(chrome_auth_timeout_seconds))
        self.driver_factory = driver_factory
        self.recovery_message_timeout_seconds = recovery_message_timeout_seconds
        self.cache = ChatCache(self.cache_path)
        self.runtime = SchedulerRuntime(self.state_path, self.state_path)
        self.browser = BrowserSession("https://chatgpt.com", self._new_driver)
        self.tracker = ConversationTracker(
            self.cache,
            ensure_driver=self.browser.ensure_driver,
            ensure_route=self.browser.ensure_conversation_route,
            current_driver=lambda: self.browser.driver,
            recovery_message_timeout_seconds=lambda: self.recovery_message_timeout_seconds,
        )

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
            ownership_prefix=_CONVERSATION_WINDOW_PREFIX,
        )

    async def _detach_for_unattended_mode(self) -> int:
        detached = 0
        driver = self.browser.driver
        for context, active in list(self.tracker.active.items()):
            self.cache.mark_unattended(active.conversation_id)
            if driver is not None:
                try:
                    await driver.close_context(context)
                except Exception:
                    logger.debug(
                        "Could not close conversation-worker tab while entering Machine Gun Mode",
                        exc_info=True,
                    )
            self.tracker.active.pop(context, None)
            detached += 1
        detached += self.cache.mark_active_unattended()
        return detached

    async def _dismiss_history_rate_limits(self, driver: PlaywrightDriver) -> bool:
        limited = False
        contexts: list[str | None] = [None, *list(self.tracker.active)]
        for context in contexts:
            try:
                limited = await driver.dismiss_history_rate_limit(context=context) or limited
            except Exception:
                logger.debug("Could not inspect ChatGPT history rate-limit modal", exc_info=True)
        # Conversation-history throttling may prevent transcript reads, but it
        # does not imply that sending prompts is rate limited. Keep the pause local
        # to the conversation worker instead of blocking the delivery worker.
        return limited

    async def run_once(self) -> bool:
        if self.runtime.unattended_mode():
            detached = await self._detach_for_unattended_mode()
            return detached > 0

        if self.runtime.global_backoff_remaining() > 0:
            return False

        driver = await self.browser.ensure_driver()
        await driver.cleanup_orphan_pages()
        if await self._dismiss_history_rate_limits(driver):
            return False

        recovered = await self.tracker.recover_cached_conversations()
        await self.tracker.poll_active_conversations()
        if await self._dismiss_history_rate_limits(driver):
            return False
        return recovered > 0 or bool(self.tracker.active)

    async def _watchdog_heartbeat(self) -> None:
        while True:
            await asyncio.sleep(_WATCHDOG_HEARTBEAT_SECONDS)
            notify_watchdog()

    async def run_forever(self) -> None:
        logger.info(
            "Prompta conversation worker tracking %s via durable SQLite handoff",
            self.cache_path,
        )
        health = ServiceHealthStore(self.runtime.state_path)
        watchdog_task = asyncio.create_task(self._watchdog_heartbeat())
        try:
            while True:
                health.begin_activity("conversation_worker", "poll")
                notify_watchdog()
                try:
                    did_work = await self.run_once()
                finally:
                    health.end_activity("conversation_worker", "poll")
                    notify_watchdog()
                await asyncio.sleep(0.25 if did_work else _DEFAULT_POLL_SECONDS)
        finally:
            watchdog_task.cancel()
            with suppress(asyncio.CancelledError):
                await watchdog_task

    async def close(self) -> None:
        for context, active in list(self.tracker.active.items()):
            self.cache.release_browser_context(
                active.conversation_id,
                context_id=context,
            )
        self.tracker.active.clear()
        driver = self.browser.driver
        if driver is not None:
            await driver.close()
            self.browser.driver = None
        self.cache.close()


def run(
    state_path: Path = DEFAULT_RUNTIME_PATH,
    *,
    cache_path: Path | None = None,
    chrome_profile: Path | None = None,
    chrome_path: str = "/usr/bin/chromium",
    chrome_debugger_address: str | None = None,
    flaresolverr_url: str | None = None,
    chrome_auth_timeout_seconds: float = 30.0,
) -> None:
    async def serve() -> None:
        worker = ConversationWorker(
            state_path,
            cache_path=cache_path,
            chrome_profile=chrome_profile,
            chrome_path=chrome_path,
            chrome_debugger_address=chrome_debugger_address,
            flaresolverr_url=flaresolverr_url,
            chrome_auth_timeout_seconds=chrome_auth_timeout_seconds,
        )
        try:
            await worker.run_forever()
        finally:
            await worker.close()

    asyncio.run(serve())


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the Prompta conversation tracking worker")
    parser.add_argument("--state", type=Path, default=DEFAULT_RUNTIME_PATH)
    parser.add_argument("--cache", type=Path)
    parser.add_argument(
        "--chrome-profile",
        type=Path,
        default=(
            Path(os.environ["PROMPTA_CHROME_PROFILE"])
            if os.environ.get("PROMPTA_CHROME_PROFILE")
            else None
        ),
    )
    parser.add_argument(
        "--chrome-path",
        default=os.environ.get("PROMPTA_CHROME_PATH", "/usr/bin/chromium"),
    )
    parser.add_argument(
        "--chrome-debugger-address",
        default=os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9222"),
    )
    parser.add_argument(
        "--flaresolverr-url",
        default=os.environ.get("PROMPTA_FLARESOLVERR_URL"),
    )
    parser.add_argument(
        "--chrome-auth-timeout-seconds",
        type=float,
        default=float(os.environ.get("PROMPTA_CHROME_AUTH_TIMEOUT_SECONDS", "30")),
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    run(
        args.state,
        cache_path=args.cache,
        chrome_profile=args.chrome_profile,
        chrome_path=args.chrome_path,
        chrome_debugger_address=args.chrome_debugger_address,
        flaresolverr_url=args.flaresolverr_url,
        chrome_auth_timeout_seconds=args.chrome_auth_timeout_seconds,
    )


if __name__ == "__main__":
    main()
