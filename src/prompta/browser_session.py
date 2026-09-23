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

    async def maximize_effort_slider(self, driver: BrowserDriver) -> None:
        await driver.maximize_effort_slider()

    async def ensure_high_effort(
        self,
        driver: BrowserDriver,
        *,
        effort_trigger_info,
        maximize_effort_slider,
        pointer_click,
    ) -> None:
        target_model = "GPT-6 Astra"

        def is_target_selected(info: dict[str, Any]) -> bool:
            effort = str(info.get("text") or "").strip().casefold()
            label = str(info.get("label") or "").strip().casefold()
            return effort in {"max", "extra high"} and target_model.casefold() in label

        trigger = await effort_trigger_info(driver)
        if is_target_selected(trigger):
            logger.info("Prompta verified thinking effort=GPT-6 Astra Max")
            return
        target_model_selected = (
            target_model.casefold() in str(trigger.get("label") or "").casefold()
        )

        for attempt in range(2):
            try:
                await pointer_click(driver, float(trigger["x"]), float(trigger["y"]))
                break
            except RuntimeError as exc:
                if "out of bounds" not in str(exc).casefold() or attempt > 0:
                    raise
                trigger = await effort_trigger_info(driver)

        if not target_model_selected:
            await driver.select_effort_model(target_model)

        await maximize_effort_slider(driver)

        deadline = asyncio.get_running_loop().time() + 2.0
        while asyncio.get_running_loop().time() < deadline:
            value = await driver.high_effort_slider_value()
            maximum = await driver.high_effort_slider_max_value()
            if value and maximum and value == maximum:
                break
            await asyncio.sleep(0.1)
        else:
            raise RuntimeError("ChatGPT thinking-effort slider did not reach maximum")

        await driver._perform_actions(
            driver.context,
            [
                {
                    "type": "key",
                    "id": "keyboard",
                    "actions": [
                        {"type": "keyDown", "value": "\ue00c"},
                        {"type": "keyUp", "value": "\ue00c"},
                    ],
                }
            ],
        )
        await asyncio.sleep(0.2)

        verified = await effort_trigger_info(driver)
        if not is_target_selected(verified):
            raise RuntimeError(
                "ChatGPT thinking effort verification failed: "
                f"{verified.get('label') or verified.get('text')!r}"
            )
        logger.info("Prompta set and verified thinking effort=GPT-6 Astra Max")
