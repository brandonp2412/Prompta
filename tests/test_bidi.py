from __future__ import annotations

import json
from unittest.mock import AsyncMock

import pytest

from prompta.bidi import FirefoxBiDiDriver


@pytest.mark.asyncio
async def test_click_send_uses_webdriver_pointer_input() -> None:
    driver = FirefoxBiDiDriver("ws://unused")
    driver.context = "context-1"
    driver.eval = AsyncMock(return_value=json.dumps({"x": 120.5, "y": 48.2}))  # type: ignore[method-assign]
    driver._call = AsyncMock()  # type: ignore[method-assign]

    await driver.click_send()

    assert driver._call.await_count == 2
    perform = driver._call.await_args_list[0]
    assert perform.args[0] == "input.performActions"
    actions = perform.args[1]["actions"][0]
    assert actions["type"] == "pointer"
    assert actions["parameters"] == {"pointerType": "mouse"}
    assert actions["actions"] == [
        {
            "type": "pointerMove",
            "x": 120,
            "y": 48,
            "duration": 0,
            "origin": "viewport",
        },
        {"type": "pointerDown", "button": 0},
        {"type": "pointerUp", "button": 0},
    ]
    release = driver._call.await_args_list[1]
    assert release.args == ("input.releaseActions", {"context": "context-1"})
