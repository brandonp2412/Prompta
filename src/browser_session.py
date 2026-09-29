from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from .playwright_driver import PlaywrightDriver

logger = logging.getLogger(__name__)

BrowserDriver = PlaywrightDriver
DriverFactory = Callable[[], BrowserDriver]

_EFFORT_PREFERENCE_RETRY_SECONDS = 5 * 60.0


class BrowserSession:
    def __init__(self, browser_url: str, driver_factory: DriverFactory | None = None) -> None:
        self.browser_url = browser_url
        self.driver_factory = driver_factory
        self.driver: BrowserDriver | None = None
        self._next_effort_preference_retry_at = 0.0

    async def ensure_driver(self) -> BrowserDriver:
        if self.driver is None:
            if self.driver_factory is None:
                raise RuntimeError("Chromium driver factory is not configured")
            self.driver = self.driver_factory()
        if not self.driver.is_connected:
            await self.driver.connect()
        return self.driver

    async def ensure_high_effort(self, driver: BrowserDriver) -> None:
        await driver.ensure_chat_surface()

        now = asyncio.get_running_loop().time()
        if now < self._next_effort_preference_retry_at:
            return

        try:
            await driver.select_effort_model("GPT-5.6 Sol")
            power = await driver.set_effort_power_position(3)
            if str(power.get("text") or "").strip().casefold() != "high":
                raise RuntimeError(f"ChatGPT High effort verification failed: {power!r}")
            if "upgrade required" in str(power.get("description") or "").casefold():
                raise RuntimeError("ChatGPT High effort unexpectedly requires an upgrade")
        except RuntimeError as exc:
            if getattr(driver, "needs_browser_restart", False) is True:
                raise
            self._next_effort_preference_retry_at = now + _EFFORT_PREFERENCE_RETRY_SECONDS
            await driver.dismiss_transient_controls()
            logger.warning(
                "Prompta could not set preferred model/effort; continuing with the "
                "current Chat setting and retrying later: %s",
                exc,
            )
            return

        self._next_effort_preference_retry_at = 0.0
        await driver.dismiss_transient_controls()
        logger.info("Prompta set and verified model=GPT-5.6 Sol effort=High")
