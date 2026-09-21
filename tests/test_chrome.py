from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import WebDriverException

from prompta.chrome import ChromeDriverDriver


def test_create_driver_uses_dedicated_profile_and_chromedriver(tmp_path: Path) -> None:
    profile = tmp_path / "chrome-profile"
    fake_driver = MagicMock()

    with (
        patch("prompta.chrome.Service") as service_type,
        patch("prompta.chrome.webdriver.Chrome", return_value=fake_driver) as chrome_type,
    ):
        driver = ChromeDriverDriver(
            profile=profile,
            chrome_path="/custom/chromium",
            chromedriver_path="/custom/chromedriver",
            headless=True,
        )
        created = driver._create_driver()

    assert created is fake_driver
    service_type.assert_called_once_with(executable_path="/custom/chromedriver")
    options = chrome_type.call_args.kwargs["options"]
    assert options.binary_location == "/custom/chromium"
    assert f"--user-data-dir={profile.resolve()}" in options.arguments
    assert "--profile-directory=Default" in options.arguments
    assert "--headless=new" in options.arguments
    assert "--password-store=basic" in options.arguments


@pytest.mark.asyncio
async def test_eval_switches_to_requested_window() -> None:
    selenium = MagicMock()
    selenium.current_window_handle = "other"
    selenium.execute_script.return_value = "value"
    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "default"

    result = await driver.eval("location.pathname", context="target")

    assert result == "value"
    selenium.switch_to.window.assert_called_once_with("target")
    selenium.execute_script.assert_called_once_with("return (location.pathname);")
    assert driver.context == "target"


@pytest.mark.asyncio
async def test_async_eval_unwraps_promise_result() -> None:
    selenium = MagicMock()
    selenium.current_window_handle = "default"
    selenium.execute_async_script.return_value = {"ok": True, "value": "token"}
    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "default"

    result = await driver.eval("Promise.resolve('token')", await_promise=True)

    assert result == "token"
    script = selenium.execute_async_script.call_args.args[0]
    assert "Promise.resolve" in script


@pytest.mark.asyncio
async def test_close_tolerates_already_dead_driver() -> None:
    selenium = MagicMock()
    selenium.quit.side_effect = WebDriverException("gone")
    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "window"

    await driver.close()

    assert driver._driver is None
    assert driver.context == ""
    assert driver.is_connected is False


@pytest.mark.asyncio
async def test_perform_actions_uses_w3c_actions() -> None:
    selenium = MagicMock()
    selenium.current_window_handle = "window"
    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "window"
    actions: list[dict[str, Any]] = [
        {
            "type": "key",
            "id": "keyboard",
            "actions": [
                {"type": "keyDown", "value": "x"},
                {"type": "keyUp", "value": "x"},
            ],
        }
    ]

    await driver._perform_actions("window", actions)

    assert selenium.execute.call_count == 2
    assert selenium.execute.call_args_list[0].args[1] == {"actions": actions}
