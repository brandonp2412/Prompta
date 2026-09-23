from __future__ import annotations

import inspect
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import pytest_asyncio
from playwright.async_api import async_playwright

from prompta.chrome import ChromeDriverDriver
from prompta.playwright_driver import (
    ChromeDebuggerUnavailableError,
    PlaywrightDriver,
)
from prompta.webdriver import BrowsingContextUnavailableError


@pytest_asyncio.fixture
async def live_driver(tmp_path: Path):
    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(
        executable_path="/usr/bin/chromium",
        headless=True,
    )
    context = await browser.new_context()
    page = await context.new_page()
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    driver._browser = browser
    driver._browser_context = context
    driver._connected = True
    driver.context = driver._register_page(page, owned=True)
    try:
        yield driver, page
    finally:
        await browser.close()
        await playwright.stop()


def test_legacy_chromedriver_name_is_playwright_compatibility_alias() -> None:
    assert ChromeDriverDriver is PlaywrightDriver


def test_runtime_source_has_no_selenium_imports() -> None:
    source = inspect.getsource(PlaywrightDriver)
    assert "selenium" not in source.casefold()
    pyproject = Path("pyproject.toml").read_text()
    assert '"selenium' not in pyproject.casefold()
    assert '"playwright' in pyproject.casefold()


@pytest.mark.asyncio
async def test_composer_prefers_semantic_textbox_and_fill(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea id="decoy" style="display:none"></textarea>
        <textarea aria-label="Message ChatGPT"></textarea>
        """
    )

    await driver.type_message("semantic hello")

    assert (
        await page.get_by_role("textbox", name="Message ChatGPT").input_value() == "semantic hello"
    )


@pytest.mark.asyncio
async def test_send_prefers_button_accessible_name(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT">hello</textarea>
        <button aria-label="Send prompt" onclick="window.sent=(window.sent||0)+1">icon</button>
        """
    )

    await driver.click_send_button(timeout=0.2)

    assert await page.evaluate("window.sent") == 1


@pytest.mark.asyncio
async def test_send_falls_back_to_stable_test_id(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT">hello</textarea>
        <button data-testid="send-button" onclick="window.sent=true">icon</button>
        """
    )

    await driver.click_send_button(timeout=0.2)

    assert await page.evaluate("window.sent") is True


@pytest.mark.asyncio
async def test_stop_prefers_button_accessible_name(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        '<button aria-label="Stop generating" onclick="window.stopped=true">square</button>'
    )

    assert await driver.click_stop(driver.context, timeout=0.2) is True
    assert await page.evaluate("window.stopped") is True


@pytest.mark.asyncio
async def test_login_required_uses_role_and_accessible_name(live_driver) -> None:
    driver, page = live_driver
    await page.set_content('<nav><a href="/auth/login">Log in</a></nav>')

    assert await driver.login_required() is True


@pytest.mark.asyncio
async def test_wait_for_composer_accepts_semantic_textbox_without_css_contract(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        '<div contenteditable="true" role="textbox" aria-label="Ask ChatGPT"></div>'
    )

    await driver.wait_for_composer(timeout=0.2)


@pytest.mark.asyncio
async def test_dom_state_does_not_treat_conversation_rate_limit_text_as_banner(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <div data-message-author-role="user" data-message-id="u1">
          Please explain what a rate limit is.
        </div>
        """
    )

    state = await driver.dom_state()

    assert state["rate_limit_text"] == ""
    assert state["last_user_id"] == "u1"
    assert "rate limit" in state["last_user_text"]


@pytest.mark.asyncio
async def test_dom_state_reads_and_dismisses_semantic_rate_limit_dialog(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <div role="dialog">
          <p>Too many requests. Try again later.</p>
          <button onclick="this.closest('[role=dialog]').remove()">Got it</button>
        </div>
        """
    )

    state = await driver.dom_state()

    assert "Too many requests" in state["rate_limit_text"]
    assert await page.get_by_role("dialog").count() == 0


@pytest.mark.asyncio
async def test_dom_state_ignores_generic_rate_limit_alert(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <div role="alert">Too many requests from an unrelated notification.</div>
        """
    )

    state = await driver.dom_state()

    assert state["rate_limit_text"] == ""


@pytest.mark.asyncio
async def test_dom_state_dismisses_history_throttling_without_rate_limiting_send(
    live_driver,
) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <div role="dialog" data-testid="modal-conversation-history-rate-limit">
          <p>Too many requests while loading conversation history.</p>
          <button onclick="this.closest('[role=dialog]').remove()">Got it</button>
        </div>
        """
    )

    state = await driver.dom_state()

    assert state["rate_limit_text"] == ""
    assert await page.get_by_role("dialog").count() == 0


@pytest.mark.asyncio
async def test_hidden_file_input_is_supported_as_non_semantic_fallback(
    live_driver,
    tmp_path: Path,
) -> None:
    driver, page = live_driver
    attachment = tmp_path / "note.txt"
    attachment.write_text("hello")
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <input type="file" style="display:none">
        """
    )

    await driver.attach_files([str(attachment)])

    assert (
        await page.locator('input[type="file"]').evaluate("input => input.files[0].name")
        == "note.txt"
    )


@pytest.mark.asyncio
async def test_effort_trigger_uses_button_role(live_driver) -> None:
    driver, page = live_driver
    await page.set_content('<button aria-haspopup="menu">Medium</button>')

    trigger = await driver.effort_trigger_info(timeout=0.2)

    assert trigger["text"] == "Medium"
    assert trigger["x"] > 0
    assert trigger["y"] > 0


@pytest.mark.asyncio
async def test_high_effort_slider_uses_slider_role(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        '<input type="range" min="0" max="3" value="1" aria-valuemin="0" aria-valuemax="3">'
    )

    point = await driver.high_effort_slider_point()

    assert point["x"] > 0
    assert point["y"] > 0


@pytest.mark.asyncio
async def test_history_navigation_uses_link_role(live_driver) -> None:
    driver, page = live_driver

    async def fulfill(route):
        await route.fulfill(status=200, content_type="text/html", body="<main>target</main>")

    await page.route("https://chatgpt.com/**", fulfill)
    await page.set_content('<a href="https://chatgpt.com/c/target">History item</a>')

    assert await driver.activate_history_link("/c/target") is True
    await page.wait_for_url("https://chatgpt.com/c/target")


@pytest.mark.asyncio
async def test_find_context_for_path_only_adopts_prompta_owned_pages(live_driver) -> None:
    driver, page = live_driver
    context = driver._browser_context
    assert context is not None

    async def fulfill(route):
        await route.fulfill(status=200, content_type="text/html", body="<main>chat</main>")

    await context.route("https://chatgpt.com/**", fulfill)

    user_page = await context.new_page()
    await user_page.goto("https://chatgpt.com/c/user")
    assert await driver.find_context_for_path("/c/user") is None

    owned_page = await context.new_page()
    await owned_page.goto("https://chatgpt.com/c/owned")
    await owned_page.evaluate("window.name='prompta:1:test'")

    context_id = await driver.find_context_for_path("/c/owned")

    assert context_id
    assert driver._pages[context_id] is owned_page


@pytest.mark.asyncio
async def test_page_send_probe_scripts_preserve_request_and_stream_capture(live_driver) -> None:
    driver, page = live_driver

    async def fulfill(route):
        if route.request.url.endswith("/backend-api/conversation"):
            body = '{"conversation_id":"conversation-1","type":"input_message","id":"message-1"}'
            await route.fulfill(status=200, content_type="application/json", body=body)
            return
        await route.fulfill(status=200, content_type="text/html", body="<main></main>")

    await page.route("https://chatgpt.com/**", fulfill)
    await page.goto("https://chatgpt.com/")
    await driver.arm_page_send_probe()
    await page.evaluate(
        """() => fetch("/backend-api/conversation", {
          method: "POST",
          headers: {"Content-Type": "application/json"},
          body: JSON.stringify({
            messages: [{id: "message-1"}],
            parent_message_id: "parent-1"
          })
        })"""
    )
    await page.wait_for_timeout(50)

    probe = await driver.page_send_probe()

    assert probe["message_id"] == "message-1"
    assert probe["parent_message_id"] == "parent-1"
    assert probe["conversation_id"] == "conversation-1"
    assert probe["response_status"] == 200
    assert probe["committed"] is True

    cleared = await driver.clear_page_send_probe()
    assert cleared == probe
    assert await driver.page_send_probe() == {}


@pytest.mark.asyncio
async def test_eval_passes_dynamic_values_as_playwright_arguments(live_driver) -> None:
    driver, _ = live_driver
    value = 'chat";window.injected=true;//'

    result = await driver.eval("(value) => value", argument=value)

    assert result == value


@pytest.mark.asyncio
async def test_closed_page_becomes_browsing_context_unavailable(live_driver) -> None:
    driver, page = live_driver
    await page.close()

    with pytest.raises(BrowsingContextUnavailableError):
        await driver.eval("location.href")


def test_debugger_probe_requires_cdp_websocket_url(tmp_path: Path) -> None:
    driver = PlaywrightDriver(
        profile=tmp_path / "profile",
        debugger_address="127.0.0.1:9222",
    )
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps({}).encode()

    with (
        patch("prompta.playwright_driver.urlopen", return_value=response),
        pytest.raises(ChromeDebuggerUnavailableError, match="127.0.0.1:9222"),
    ):
        driver._assert_debugger_available()


def test_debugger_probe_accepts_valid_cdp_endpoint(tmp_path: Path) -> None:
    driver = PlaywrightDriver(
        profile=tmp_path / "profile",
        debugger_address="127.0.0.1:9222",
    )
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {"webSocketDebuggerUrl": "ws://127.0.0.1/devtools/browser/abc"}
    ).encode()

    with patch("prompta.playwright_driver.urlopen", return_value=response):
        driver._assert_debugger_available()


def test_flaresolverr_filters_to_cloudflare_cookies(tmp_path: Path) -> None:
    driver = PlaywrightDriver(
        profile=tmp_path / "profile",
        flaresolverr_url="http://127.0.0.1:8191",
    )
    response = MagicMock()
    response.__enter__.return_value.read.return_value = json.dumps(
        {
            "status": "ok",
            "solution": {
                "userAgent": "browser-ua",
                "cookies": [
                    {"name": "cf_clearance", "value": "ok"},
                    {"name": "session", "value": "private"},
                ],
            },
        }
    ).encode()

    with patch("prompta.playwright_driver.urlopen", return_value=response):
        cookies = driver._request_flaresolverr("https://chatgpt.com/", "browser-ua")

    assert cookies == [{"name": "cf_clearance", "value": "ok"}]


def test_semantic_locators_are_first_in_composer_and_button_helpers() -> None:
    composer_source = inspect.getsource(PlaywrightDriver._composer)
    button_source = inspect.getsource(PlaywrightDriver._semantic_button)

    assert composer_source.index("get_by_role") < composer_source.index("locator(selector)")
    assert button_source.index("get_by_role") < button_source.index("get_by_test_id")
    assert button_source.index("get_by_test_id") < button_source.index("locator(selector)")
