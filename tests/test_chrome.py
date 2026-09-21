from __future__ import annotations

import asyncio
import json
import threading
import time
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, PropertyMock, patch

import pytest
from selenium.common.exceptions import NoSuchElementException, WebDriverException
from selenium.webdriver.common.by import By
from urllib3.connectionpool import HTTPConnectionPool
from urllib3.exceptions import ReadTimeoutError

from prompta.chrome import ChromeDebuggerUnavailableError, ChromeDriverDriver, _PromptaChrome


def test_prompta_chrome_applies_timeout_before_start_session() -> None:
    service = MagicMock()
    service.service_url = "http://127.0.0.1:4444"
    options = MagicMock()
    options._ignore_local_proxy = True
    executor = MagicMock()
    client_config = MagicMock()

    with (
        patch("prompta.chrome.ClientConfig", return_value=client_config) as config_type,
        patch("prompta.chrome.ChromiumRemoteConnection", return_value=executor) as connection_type,
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
    remote_init.assert_called_once_with(driver, command_executor=executor, options=options)


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


def test_attached_debugger_unavailable_fails_fast(tmp_path: Path) -> None:
    driver = ChromeDriverDriver(
        profile=tmp_path / "chrome-profile",
        debugger_address="127.0.0.1:9222",
    )

    with (
        patch("prompta.chrome.urlopen", side_effect=OSError("connection refused")),
        pytest.raises(ChromeDebuggerUnavailableError, match="127.0.0.1:9222"),
    ):
        driver._assert_debugger_available()


@pytest.mark.asyncio
async def test_connect_does_not_poison_session_when_debugger_is_offline(tmp_path: Path) -> None:
    driver = ChromeDriverDriver(
        profile=tmp_path / "chrome-profile",
        debugger_address="127.0.0.1:9222",
    )

    with (
        patch.object(
            driver,
            "_assert_debugger_available",
            side_effect=ChromeDebuggerUnavailableError("offline"),
        ),
        patch.object(driver, "_cleanup_stale_owned_contexts", new_callable=AsyncMock) as cleanup,
        patch.object(driver, "_create_driver_session", new_callable=AsyncMock) as create_session,
        pytest.raises(ChromeDebuggerUnavailableError, match="offline"),
    ):
        await driver.connect()

    cleanup.assert_not_awaited()
    create_session.assert_not_awaited()
    assert driver.needs_browser_restart is False


@pytest.mark.asyncio
async def test_create_driver_session_retries_attached_browser_timeout() -> None:
    driver = ChromeDriverDriver(
        profile=Path("/tmp/profile"),
        debugger_address="127.0.0.1:9222",
    )
    created = MagicMock()
    timeout = ReadTimeoutError(
        HTTPConnectionPool("localhost", port=4444),
        "/session",
        "timed out",
    )

    with (
        patch.object(driver, "_create_driver", side_effect=[timeout, created]) as create_driver,
        patch("prompta.chrome.asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        result = await driver._create_driver_session()

    assert result is created
    assert create_driver.call_count == 2
    sleep.assert_awaited_once_with(0.5)
    assert driver.needs_browser_restart is False


@pytest.mark.asyncio
async def test_create_driver_session_does_not_retry_owned_browser_timeout() -> None:
    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    timeout = ReadTimeoutError(
        HTTPConnectionPool("localhost", port=4444),
        "/session",
        "timed out",
    )

    with (
        patch.object(driver, "_create_driver", side_effect=timeout) as create_driver,
        patch("prompta.chrome.asyncio.sleep", new_callable=AsyncMock) as sleep,
    ):
        with pytest.raises(
            RuntimeError, match="create ChromeDriver session: .*browser restart required"
        ):
            await driver._create_driver_session()

    create_driver.assert_called_once_with()
    sleep.assert_not_awaited()
    assert driver.needs_browser_restart is True


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


def test_debugger_cleanup_closes_only_owned_open_targets() -> None:
    driver = ChromeDriverDriver(
        profile=Path("/tmp/profile"),
        debugger_address="127.0.0.1:9222",
    )
    listing = MagicMock()
    listing.read.return_value = json.dumps([{"id": "target"}, {"id": "unowned"}]).encode()
    listing.__enter__.return_value = listing
    closing = MagicMock()
    closing.__enter__.return_value = closing

    with patch("prompta.chrome.urlopen", side_effect=[listing, closing]) as open_url:
        unresolved = driver._close_debugger_targets({"target", "already-gone"})

    assert unresolved == set()
    assert open_url.call_count == 2
    assert open_url.call_args_list[0].args[0] == "http://127.0.0.1:9222/json/list"
    request = open_url.call_args_list[1].args[0]
    assert request.full_url == "http://127.0.0.1:9222/json/close/target"
    assert request.get_method() == "PUT"


def test_owned_context_registry_tracks_only_prompta_tabs(tmp_path: Path) -> None:
    profile = tmp_path / "chrome-profile"
    driver = ChromeDriverDriver(
        profile=profile,
        debugger_address="127.0.0.1:9222",
    )

    driver._remember_owned_context("prompta-tab")

    registry = profile.with_name("chrome-profile.owned-contexts.json")
    assert json.loads(registry.read_text()) == ["prompta-tab"]

    driver._forget_owned_context("prompta-tab")

    assert not registry.exists()


@pytest.mark.asyncio
async def test_stale_owned_context_cleanup_preserves_only_failed_targets(tmp_path: Path) -> None:
    profile = tmp_path / "chrome-profile"
    registry = profile.with_name("chrome-profile.owned-contexts.json")
    registry.write_text(json.dumps(["already-gone", "still-open"]))
    driver = ChromeDriverDriver(
        profile=profile,
        debugger_address="127.0.0.1:9222",
    )

    with patch.object(
        driver,
        "_close_debugger_targets",
        return_value={"still-open"},
    ) as close_targets:
        await driver._cleanup_stale_owned_contexts()

    close_targets.assert_called_once_with({"already-gone", "still-open"})
    assert driver._owned_contexts == {"still-open"}
    assert json.loads(registry.read_text()) == ["still-open"]


@pytest.mark.asyncio
async def test_connect_cleans_stale_targets_before_creating_driver(tmp_path: Path) -> None:
    driver = ChromeDriverDriver(
        profile=tmp_path / "chrome-profile",
        debugger_address="127.0.0.1:9222",
    )
    selenium = MagicMock()
    selenium.window_handles = ["user-tab"]
    selenium.current_window_handle = "prompta-tab"
    order: list[str] = []

    async def cleanup() -> None:
        order.append("cleanup")

    async def create_session() -> MagicMock:
        order.append("create")
        return selenium

    with (
        patch.object(driver, "_assert_debugger_available"),
        patch.object(driver, "_cleanup_stale_owned_contexts", side_effect=cleanup),
        patch.object(driver, "_create_driver_session", side_effect=create_session),
        patch.object(driver, "navigate", new_callable=AsyncMock),
        patch.object(driver, "login_required", new_callable=AsyncMock, return_value=False),
        patch.object(driver, "ensure_token", new_callable=AsyncMock, return_value=True),
    ):
        await driver.connect()

    assert order[:2] == ["cleanup", "create"]
    assert "prompta-tab" in driver._owned_contexts


@pytest.mark.asyncio
async def test_close_uses_debugger_cleanup_when_webdriver_is_unavailable() -> None:
    selenium = MagicMock()
    type(selenium).window_handles = PropertyMock(side_effect=WebDriverException("gone"))
    driver = ChromeDriverDriver(
        profile=Path("/tmp/profile"),
        debugger_address="127.0.0.1:9222",
    )
    driver._driver = selenium
    driver.context = "prompta-tab"
    driver._owned_contexts.add("prompta-tab")

    with patch.object(driver, "_close_debugger_targets") as close_targets:
        await driver.close()

    close_targets.assert_called_once_with({"prompta-tab"})
    selenium.service.stop.assert_called_once_with()
    selenium.command_executor.close.assert_called_once_with()


@pytest.mark.asyncio
async def test_close_context_preserves_default_when_closing_background_tab() -> None:
    selenium = MagicMock()
    selenium.window_handles = ["default", "other"]
    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "default"
    driver._owned_contexts.add("target")

    await driver.close_context("target")

    assert [call.args for call in selenium.switch_to.window.call_args_list] == [
        ("target",),
        ("default",),
    ]
    assert driver.context == "default"
    assert "target" not in driver._owned_contexts


@pytest.mark.asyncio
async def test_close_context_moves_default_when_closing_default_tab() -> None:
    selenium = MagicMock()
    selenium.window_handles = ["fallback"]
    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "target"
    driver._owned_contexts.add("target")

    await driver.close_context("target")

    assert [call.args for call in selenium.switch_to.window.call_args_list] == [
        ("target",),
        ("fallback",),
    ]
    assert driver.context == "fallback"
    assert "target" not in driver._owned_contexts


@pytest.mark.asyncio
async def test_close_context_keeps_failed_tab_owned() -> None:
    selenium = MagicMock()
    selenium.switch_to.window.return_value = None
    selenium.close.side_effect = WebDriverException("close failed")
    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "default"
    driver._owned_contexts.add("target")

    with pytest.raises(RuntimeError, match="close Chromium tab: close failed"):
        await driver.close_context("target")

    assert "target" in driver._owned_contexts


@pytest.mark.asyncio
async def test_close_context_marks_timed_out_driver_for_restart() -> None:
    selenium = MagicMock()
    pool = HTTPConnectionPool("localhost", port=4444)
    selenium.switch_to.window.side_effect = ReadTimeoutError(
        pool, "/session/id/window", "timed out"
    )
    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "default"

    with pytest.raises(RuntimeError, match="close Chromium tab: .*browser restart required"):
        await driver.close_context("target")

    assert driver.needs_browser_restart is True


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
    assert any(
        call.args == ("upload-tab",) for call in selenium.switch_to.window.call_args_list[1:]
    )
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
async def test_click_stop_uses_chromedriver_instead_of_bidi() -> None:
    selenium = MagicMock()
    selenium.current_window_handle = "window"

    stop = MagicMock()
    stop.is_displayed.return_value = True
    stop.is_enabled.return_value = True
    stop.get_attribute.return_value = None

    def find_elements(by: str, selector: str) -> list[MagicMock]:
        assert by == By.CSS_SELECTOR
        return [stop] if selector == '[data-testid="stop-button"]' else []

    selenium.find_elements.side_effect = find_elements

    driver = ChromeDriverDriver(profile=Path("/tmp/profile"))
    driver._driver = selenium
    driver.context = "window"
    driver._call = AsyncMock(return_value={"type": "success"})  # type: ignore[method-assign]

    assert await driver.click_stop("window", timeout=0.1) is True

    stop.click.assert_called_once_with()
    driver._call.assert_not_awaited()


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
async def test_new_tab_closes_created_context_when_navigation_fails(tmp_path: Path) -> None:
    selenium = MagicMock()
    selenium.current_window_handle = "new-context"
    selenium.window_handles = ["default-context"]
    driver = ChromeDriverDriver(profile=tmp_path / "profile")
    driver._driver = selenium
    driver.context = "default-context"

    with (
        patch.object(
            driver,
            "navigate",
            new_callable=AsyncMock,
            side_effect=RuntimeError("navigation failed"),
        ),
        pytest.raises(RuntimeError, match="navigation failed"),
    ):
        await driver.new_tab("https://chatgpt.com/c/test")

    selenium.close.assert_called_once_with()
    assert "new-context" not in driver._owned_contexts
    assert driver.context == "default-context"


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
@pytest.mark.parametrize(
    "message",
    ["no such window", "target window already closed", "web view not found"],
)
async def test_eval_marks_closed_chromium_window_for_restart(message: str) -> None:
    selenium = MagicMock()
    selenium.current_window_handle = "window"
    selenium.execute_script.side_effect = WebDriverException(message)
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
