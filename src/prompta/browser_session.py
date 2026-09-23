from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable

from .playwright_driver import PlaywrightDriver

logger = logging.getLogger(__name__)

BrowserDriver = PlaywrightDriver
DriverFactory = Callable[[], BrowserDriver]


class BrowserSession:
    def __init__(self, browser_url: str, driver_factory: DriverFactory | None = None) -> None:
        self.browser_url = browser_url
        self.driver_factory = driver_factory
        self.driver: BrowserDriver | None = None

    async def ensure_driver(self) -> BrowserDriver:
        driver = self.driver
        if driver is None:
            if self.driver_factory is None:
                raise RuntimeError("Chromium driver factory is not configured")
            driver = self.driver_factory()
            self.driver = driver

        if not driver.is_connected:
            await driver.connect()
        return driver

    async def ensure_conversation_route(
        self,
        driver: BrowserDriver,
        expected_path: str,
        *,
        context: str | None = None,
    ) -> None:
        expected = expected_path.rstrip("/")
        deadline = asyncio.get_running_loop().time() + 10.0
        activated_history = False
        navigated = False
        context_args = {} if context is None else {"context": context}

        async def current_path() -> str:
            value = await driver.eval("location.pathname", **context_args)
            return str(value or "").rstrip("/")

        path = await current_path()
        while path != expected and asyncio.get_running_loop().time() < deadline:
            if path in {"", "/"} and not activated_history:
                activated_history = await driver.activate_history_link(expected, **context_args)
                if not activated_history and not navigated:
                    await driver.navigate(f"https://chatgpt.com{expected}", **context_args)
                    navigated = True
            await asyncio.sleep(0.25)
            path = await current_path()
        if path == expected:
            return
        raise RuntimeError(
            f"ChatGPT opened unexpected conversation path {path!r}; expected {expected!r}"
        )

    async def ensure_high_effort(self, driver: BrowserDriver) -> None:
        trigger = await driver.effort_trigger_info()
        if str(trigger.get("text") or "").strip().casefold() == "high":
            logger.info("Prompta verified thinking effort=High")
            return
        for attempt in range(2):
            try:
                await driver._click_viewport_point(
                    driver.context, float(trigger["x"]), float(trigger["y"])
                )
                break
            except RuntimeError as exc:
                if "out of bounds" not in str(exc).casefold() or attempt > 0:
                    raise
                trigger = await driver.effort_trigger_info()
        for attempt in range(2):
            point = await driver.high_effort_slider_point()
            try:
                await driver._click_viewport_point(driver.context, point["x"], point["y"])
                break
            except RuntimeError as exc:
                if "out of bounds" not in str(exc).casefold() or attempt > 0:
                    raise
        deadline = asyncio.get_running_loop().time() + 2.0
        while asyncio.get_running_loop().time() < deadline:
            if await driver.high_effort_slider_value() == "2":
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("ChatGPT thinking-effort slider did not reach High")
        await driver._page(driver.context).keyboard.press("Escape")
        await asyncio.sleep(0.2)
        verified = await driver.effort_trigger_info()
        if str(verified.get("text") or "").strip().casefold() != "high":
            raise RuntimeError(
                f"ChatGPT thinking effort verification failed: {verified.get('text')!r}"
            )
        logger.info("Prompta set and verified thinking effort=High")
