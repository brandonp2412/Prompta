from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.exceptions import ReadTimeoutError

from prompta.chrome import ChromeDriverDriver, _PromptaChrome


def test_prompta_chrome_applies_timeout_before_start_session() -> None:
    service = MagicMock()
    service.service_url = "http://127.0.0.1:4444"
    options = MagicMock()
    options._ignore_local_proxy = True
    executor = MagicMock()
    client_config = MagicMock()

    with (
        patch("prompta.chrome.ClientConfig", return_value=client_config) as config_type,
        patch(
            "prompta.chrome.ChromiumRemoteConnection", return_value=executor
        ) as connection_type,
        patch("prompta.chrome.RemoteWebDriver.__init__", return_value=None) as remote_init,
    ):
        driver = _PromptaChrome(service=service, options=options)

    service.start.assert_called_once_with()
    config_type.assert_called_once_with(
        remote_server_addr=service.service_url, keep_alive=True, timeout=30.0
    )
    connection_type.assert_called_once_with(
        remote_server_addr=service.service_url,
        browser_name="chrome",
        vendor_prefix="goog",
        keep_alive=True,
        ignore_proxy=True,
        client_config=client_config,
    )
    remote_init.assert_called_once_with(
        driver, command_executor=executor, options=options
    )


def test_create_driver_uses_dedicated_profile_and_chromedriver(tmp_path: Path) -> None:
    profile = tmp_path / "chrome-profile"
    fake_driver = MagicMock()

    with (
        patch("prompta.chrome.Service") as service_type,
        patch("prompta.chrome._PromptaChrome", return_value=fake_driver) as chrome_type,
    ):
        driver = ChromeDriverDriver(
            profile=profile,
            chrome_path="/custom/chromium",
            chromedriver_path="/custom/chromedriver",
            headless=True,
        )
        created = driver._create_driver()

    assert created is fake_driver
    assert fake_driver.command_executor._client_config.timeout == 30.0
    service_type.assert_called_once_with(executable_path="/custom/chromedriver")
    options = chrome_type.call_args.kwargs["options"]
    assert options.binary_location == "/custom/chromium"
    assert f"--user-data-dir={profile.resolve()}" in options.arguments
    assert "--profile-directory=Default" in options.arguments
    assert "--headless=new" in options.arguments
    assert "--password-store=basic" in options.arguments


def test_create_driver_attaches_to_existing_browser_without_profile_args(tmp_path: Path) -> None:
    profile = tmp_path / "unused-profile"
    fake_driver = MagicMock()

    with (
        patch("prompta.chrome.Service") as service_type,
        patch("prompta.chrome._PromptaChrome", return_value=fake_driver) as chrome_type,
    ):
        driver = ChromeDriverDriver(
            profile=profile,
            chromedriver_path="/custom/chromedriver",
            debugger_address="127.0.0.1:9222",
        )
        created = driver._create_driver()

    assert created is fake_driver
    service_type.assert_called_once_with(executable_path="/custom/chromedriver")
    options = chrome_type.call_args.kwargs["options"]
    assert options.experimental_options["debuggerAddress"] == "127.0.0.1:9222"
    assert not profile.exists()
    assert not any(arg.startswith("--user-data-dir=") for arg in options.arguments)


@pytest.mark.asyncio
async def test_close_detaches_without_quitting_existing_browser() -> None:
    selenium = MagicMock()
    selenium.window_handles = ["user-tab", "prompta-tab"]
    selenium.current_window_handle = "prompta-tab"
    driver = ChromeDriverDriver(
        profile=Path("/tmp/profile"),
        debugger_address="127.0.0.1:9222",
    )
    driver._driver = selenium
    driver.context = "prompta-tab"
    driver._owned_contexts.add("prompta-tab")

    await driver.close()

    selenium.switch_to.window.assert_called_once_with("prompta-tab")
    selenium.close.assert_called_once_with()
    selenium.quit.assert_not_called()
    selenium.service.stop.assert_called_once_with()
    selenium.command_executor.close.assert_called_once_with()
    assert driver._owned_contexts == set()


@pytest.mark.asyncio
async def test_eval_switches_to_requested_window_without_stealing_default_context() -> None:
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
    assert driver.context == "default"


@pytest.mark.asyncio
async def test_attachment_upload_returns_to_default_context_after_background_eval(
    tmp_path: Path,
) -> None:
    selenium = MagicMock()
    selenium.current_window_handle = "upload-tab"
    selenium.execute_script.side_effect = [
        "watched",
        '{"attached":true,"busy":false}',
        '{"attached":true,"busy":false}',
        '{"attached":true,"busy":false}',
    ]
    file_input = MagicMock()
    selenium.find_element.return_value = file_input

    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "upload-tab"

    await driver.eval("location.pathname", context="watch-tab")
    selenium.current_window_handle = "watch-tab"

    image = tmp_path / "image.png"
    image.write_bytes(b"not-a-real-png")
    await driver.attach_files([str(image)])

    assert driver.context == "upload-tab"
    assert selenium.switch_to.window.call_args_list[0].args == ("watch-tab",)
    assert any(call.args == ("upload-tab",) for call in selenium.switch_to.window.call_args_list[1:])
    file_input.send_keys.assert_called_once_with(str(image.resolve()))


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


@pytest.mark.asyncio
async def test_click_send_button_uses_live_chatgpt_send_element() -> None:
    selenium = MagicMock()
    selenium.current_window_handle = "window"

    composer = MagicMock()
    composer.is_displayed.return_value = True
    form = MagicMock()
    composer.find_element.return_value = form

    send = MagicMock()
    send.is_displayed.return_value = True
    send.is_enabled.return_value = True
    send.get_attribute.return_value = None

    selenium.find_elements.return_value = [composer]
    form.find_elements.return_value = [send]

    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "window"

    await driver.click_send_button(timeout=0.1)

    composer.find_element.assert_called_once_with(By.XPATH, "./ancestor::form[1]")
    form.find_elements.assert_called_once_with(By.CSS_SELECTOR, '[data-testid="send-button"]')
    send.click.assert_called_once_with()


@pytest.mark.asyncio
async def test_click_send_button_skips_aria_disabled_send_control() -> None:
    selenium = MagicMock()
    selenium.current_window_handle = "window"

    composer = MagicMock()
    composer.is_displayed.return_value = True
    form = MagicMock()
    composer.find_element.return_value = form

    disabled = MagicMock()
    disabled.is_displayed.return_value = True
    disabled.is_enabled.return_value = True
    disabled.get_attribute.return_value = "true"

    enabled = MagicMock()
    enabled.is_displayed.return_value = True
    enabled.is_enabled.return_value = True
    enabled.get_attribute.return_value = None

    selenium.find_elements.return_value = [composer]
    form.find_elements.side_effect = [[disabled], [enabled]]

    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "window"

    await driver.click_send_button(timeout=0.1)

    disabled.click.assert_not_called()
    enabled.click.assert_called_once_with()


@pytest.mark.asyncio
async def test_click_send_button_does_not_use_unscoped_generic_submit() -> None:
    selenium = MagicMock()
    selenium.current_window_handle = "window"

    composer = MagicMock()
    composer.is_displayed.return_value = True
    composer.find_element.side_effect = NoSuchElementException()

    def find_elements(by: str, selector: str) -> list[MagicMock]:
        assert by == By.CSS_SELECTOR
        if selector.startswith("#prompt-textarea"):
            return [composer]
        return []

    selenium.find_elements.side_effect = find_elements

    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "window"

    with pytest.raises(RuntimeError, match="send button did not become enabled"):
        await driver.click_send_button(timeout=0.01)

    queried = [call.args[1] for call in selenium.find_elements.call_args_list]
    assert 'button[type="submit"]' not in queried


@pytest.mark.asyncio
async def test_new_tab_marks_crashed_chromedriver_for_restart() -> None:
    selenium = MagicMock()
    selenium.switch_to.new_window.side_effect = WebDriverException("tab crashed")
    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "window"

    with pytest.raises(RuntimeError, match="browser restart required"):
        await driver.new_tab()

    assert driver.needs_browser_restart is True
    assert driver.is_connected is False


@pytest.mark.asyncio
async def test_eval_marks_chromedriver_transport_timeout_for_restart() -> None:
    selenium = MagicMock()
    selenium.current_window_handle = "window"
    selenium.execute_script.side_effect = ReadTimeoutError(
        HTTPConnectionPool("127.0.0.1", 4444), "http://127.0.0.1:4444", "timed out"
    )
    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "window"

    with pytest.raises(RuntimeError, match="browser restart required"):
        await driver.eval("location.pathname")

    assert driver.needs_browser_restart is True


@pytest.mark.asyncio
async def test_eval_serializes_chromedriver_commands() -> None:
    selenium = MagicMock()
    selenium.current_window_handle = "window"
    active = 0
    peak = 0
    guard = threading.Lock()

    def execute_script(script: str) -> str:
        nonlocal active, peak
        with guard:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with guard:
            active -= 1
        return script

    selenium.execute_script.side_effect = execute_script
    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "window"

    await asyncio.gather(driver.eval("1"), driver.eval("2"))

    assert peak == 1
