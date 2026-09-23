from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from typing import Any

from .playwright_driver import PlaywrightDriver

logger = logging.getLogger(__name__)

BrowserDriver = PlaywrightDriver
DriverFactory = Callable[[], BrowserDriver]

_EFFORT_CONTROL_TIMEOUT_SECONDS = 20.0


class BrowserSession:
    def __init__(self, browser_url: str, driver_factory: DriverFactory | None = None) -> None:
        self.browser_url = browser_url
        self.driver_factory = driver_factory
        self.driver: BrowserDriver | None = None

    async def ensure_driver(self) -> BrowserDriver:
        if self.driver is None:
            if self.driver_factory is None:
                raise RuntimeError("Chromium driver factory is not configured")
            self.driver = self.driver_factory()
        if not self.driver.is_connected:
            await self.driver.connect()
        return self.driver

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
        direct_navigation_attempted = False

        async def current_path() -> str:
            if context is None:
                return str(await driver.eval("location.pathname") or "").rstrip("/")
            return str(await driver.eval("location.pathname", context=context) or "").rstrip("/")

        path = await current_path()
        while path != expected and asyncio.get_running_loop().time() < deadline:
            if path in {"", "/"} and not activated_history:
                if context is None:
                    activated_history = await driver.activate_history_link(expected)
                else:
                    activated_history = await driver.activate_history_link(
                        expected,
                        context=context,
                    )
                if not activated_history and not direct_navigation_attempted:
                    target_url = f"https://chatgpt.com{expected}"
                    if context is None:
                        await driver.navigate(target_url)
                    else:
                        await driver.navigate(target_url, context=context)
                    direct_navigation_attempted = True
            await asyncio.sleep(0.25)
            path = await current_path()
        if path != expected:
            raise RuntimeError(
                f"ChatGPT opened unexpected conversation path {path!r}; expected {expected!r}"
            )

    async def pointer_click(self, driver: BrowserDriver, x: float, y: float) -> None:
        await driver._click_viewport_point(driver.context, x, y)

    async def effort_trigger_info(
        self,
        driver: BrowserDriver,
        *,
        timeout: float = _EFFORT_CONTROL_TIMEOUT_SECONDS,
    ) -> dict[str, Any]:
        return await driver.effort_trigger_info(timeout=timeout)

    async def ensure_high_effort(
        self,
        driver: BrowserDriver,
        *,
        effort_trigger_info,
        pointer_click,
    ) -> None:
        target_model = "GPT-5.6 Sol"
        target_effort = "high"
        target_position = 3
        await driver.ensure_chat_surface()

        trigger = await effort_trigger_info(driver)
        for attempt in range(2):
            try:
                await pointer_click(driver, float(trigger["x"]), float(trigger["y"]))
                break
            except RuntimeError as exc:
                if "out of bounds" not in str(exc).casefold() or attempt > 0:
                    raise
                trigger = await effort_trigger_info(driver)

        await driver.select_effort_model(target_model)
        power = await driver.set_effort_power_position(target_position)
        if str(power.get("text") or "").strip().casefold() != target_effort:
            raise RuntimeError(f"ChatGPT Chat-mode Power verification failed: {power!r}")
        if "upgrade required" in str(power.get("description") or "").casefold():
            raise RuntimeError("ChatGPT Chat-mode High effort unexpectedly requires an upgrade")

        await driver._perform_actions(
            driver.context,
            [
                {
                    "type": "key",
                    "id": "keyboard",
                    "actions": [
                        {"type": "keyDown", "value": ""},
                        {"type": "keyUp", "value": ""},
                    ],
                }
            ],
        )
        logger.info("Prompta set and verified Chat mode model=%s effort=High", target_model)
