from __future__ import annotations

import inspect
import json
import time
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


@pytest.mark.asyncio
async def test_cloudflare_challenge_detection_uses_visible_semantics_without_provider_ids(
    live_driver,
) -> None:
    driver, page = live_driver
    await page.set_content("<main><p>Performing security verification</p></main>")

    assert await driver._cloudflare_challenge_present() is True


@pytest.mark.asyncio
async def test_cloudflare_challenge_detection_uses_frame_title_without_provider_url(
    live_driver,
) -> None:
    driver, page = live_driver
    await page.set_content('<iframe title="Cloudflare security verification"></iframe>')

    assert await driver._cloudflare_challenge_present() is True


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
async def test_composer_ignores_message_search_label_outside_main(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <aside><input role="textbox" aria-label="Message search"></aside>
        <main><textarea aria-label="Chat with ChatGPT"></textarea></main>
        """
    )

    await driver.type_message("real composer")

    assert (
        await page.get_by_role("textbox", name="Chat with ChatGPT").input_value() == "real composer"
    )
    assert await page.get_by_role("textbox", name="Message search").input_value() == ""


@pytest.mark.asyncio
async def test_composer_prefers_main_textbox_over_sidebar_and_dialog(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <aside><input role="textbox" aria-label="Message search"></aside>
        <main><section><div role="textbox" contenteditable="true"></div></section></main>
        <div role="dialog"><textarea aria-label="Other details"></textarea></div>
        """
    )

    await driver.type_message("hello from main")

    assert await page.get_by_role("main").get_by_role("textbox").inner_text() == "hello from main"
    assert await page.get_by_role("textbox", name="Message search").input_value() == ""


@pytest.mark.asyncio
async def test_focus_composer_waits_for_chatgpt_prosemirror_hydration(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <main><textarea aria-label="Ask ChatGPT"></textarea></main>
        <script>
          setTimeout(() => {
            const editor = document.createElement("div");
            editor.contentEditable = "true";
            editor.setAttribute("role", "textbox");
            editor.setAttribute("aria-label", "Ask ChatGPT");
            editor.setAttribute("data-composer-markdown", "");
            editor.style.width = "0";
            editor.style.height = "100px";
            document.querySelector("textarea").replaceWith(editor);
          }, 150);
        </script>
        """
    )

    composer = await driver._focus_composer()

    assert await composer.get_attribute("data-composer-markdown") == ""


@pytest.mark.asyncio
async def test_focus_composer_survives_composer_data_attribute_rename(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <main>
          <div
            contenteditable="true"
            role="textbox"
            aria-label="Ask ChatGPT"
            data-renamed-composer-contract=""
            style="width:0;height:100px"
          ></div>
        </main>
        """
    )

    composer = await driver._focus_composer()

    assert await composer.get_attribute("data-renamed-composer-contract") == ""


@pytest.mark.asyncio
async def test_focus_composer_survives_textbox_role_removal(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <aside><div contenteditable="true" aria-label="Search"></div></aside>
        <main>
          <div
            contenteditable="true"
            aria-label="Ask ChatGPT"
            data-renamed-composer-contract=""
            style="width:0;height:100px"
          ></div>
        </main>
        """
    )

    composer = await driver._focus_composer()

    assert await composer.get_attribute("aria-label") == "Ask ChatGPT"


@pytest.mark.asyncio
async def test_focus_composer_survives_main_landmark_removal(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <section>
          <div
            contenteditable="true"
            role="textbox"
            data-renamed-composer-contract=""
            style="width:0;height:100px"
          ></div>
        </section>
        """
    )

    composer = await driver._focus_composer()

    assert await composer.get_attribute("data-renamed-composer-contract") == ""


@pytest.mark.asyncio
async def test_type_message_survives_chatgpt_prosemirror_hydration(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <main>
          <textarea aria-label="Ask ChatGPT"></textarea>
        </main>
        <script>
          setTimeout(() => {
            const textarea = document.querySelector("textarea");
            const editor = document.createElement("div");
            editor.contentEditable = "true";
            editor.setAttribute("role", "textbox");
            editor.setAttribute("aria-label", "Ask ChatGPT");
            editor.setAttribute("data-composer-markdown", "");
            editor.textContent = "stale failed automation draft";
            editor.style.width = "0";
            editor.style.height = "100px";
            editor.style.overflow = "hidden";
            textarea.replaceWith(editor);
          }, 150);
        </script>
        """
    )

    await driver.type_message("a scheduled automation prompt that survives hydration")

    editor = page.locator('[data-composer-markdown][contenteditable="true"]')
    assert await editor.is_visible() is False
    assert (await editor.inner_text()).strip() == (
        "a scheduled automation prompt that survives hydration"
    )


@pytest.mark.asyncio
async def test_type_message_accepts_prosemirror_autolink_spacing(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <main>
          <div
            contenteditable="true"
            role="textbox"
            aria-label="Ask ChatGPT"
            data-composer-markdown=""
          ></div>
        </main>
        <script>
          const editor = document.querySelector("[data-composer-markdown]");
          editor.addEventListener("input", () => {
            if (editor.textContent.includes("=https://")) {
              editor.textContent = editor.textContent.replace("=https://", "= https://");
            }
          });
        </script>
        """
    )

    await driver.type_message("PROMPTA_E2E_BASE_URL=https://prompta.example/c/ uv run pytest")

    assert "= https://prompta.example/c/" in (
        await page.locator("[data-composer-markdown]").inner_text()
    )


@pytest.mark.asyncio
async def test_type_message_waits_for_chatgpt_composer_state_to_settle(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <main>
          <textarea aria-label="Message ChatGPT"></textarea>
        </main>
        <script>
          const composer = document.querySelector("textarea");
          composer.addEventListener("input", () => {
            const typed = composer.value;
            composer.value = "";
            setTimeout(() => { composer.value = typed; }, 150);
          }, { once: true });
        </script>
        """
    )

    await driver.type_message("a long scheduled automation prompt")

    assert await page.get_by_role("textbox", name="Message ChatGPT").input_value() == (
        "a long scheduled automation prompt"
    )


@pytest.mark.asyncio
async def test_click_send_uses_enter_on_hydrated_composer(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <main>
          <div
            contenteditable="true"
            role="textbox"
            aria-label="Ask ChatGPT"
            data-composer-markdown=""
            onkeydown="if(event.key==='Enter'){event.preventDefault();window.sent=true}"
          >scheduled automation prompt</div>
          <button aria-label="Send prompt" disabled></button>
        </main>
        """
    )

    await driver.click_send()

    assert await page.evaluate("Boolean(window.sent)") is True


@pytest.mark.asyncio
async def test_send_prefers_main_accessible_button_over_same_named_toolbar_action(
    live_driver,
) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <header><button aria-label="Send prompt" onclick="window.wrong=true"></button></header>
        <main>
          <textarea aria-label="Message ChatGPT">hello</textarea>
          <button aria-label="Send prompt" onclick="window.sent=true"></button>
        </main>
        """
    )

    await driver.click_send_button(timeout=0.2)

    assert await page.evaluate("Boolean(window.sent)") is True
    assert await page.evaluate("Boolean(window.wrong)") is False


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
async def test_send_survives_role_and_tag_churn_inside_main(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <header>
          <button aria-label="Send prompt" onclick="window.wrong=true">toolbar</button>
        </header>
        <main>
          <textarea aria-label="Message ChatGPT">hello</textarea>
          <div aria-label="Send prompt" tabindex="0" onclick="window.sent=true">arrow</div>
        </main>
        """
    )

    await driver.click_send_button(timeout=0.2)

    assert await page.evaluate("Boolean(window.sent)") is True
    assert await page.evaluate("Boolean(window.wrong)") is False


@pytest.mark.asyncio
async def test_send_ignores_test_id_on_unlabeled_button_outside_composer(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <main><textarea aria-label="Message ChatGPT">hello</textarea></main>
        <button data-testid="send-button" onclick="window.wrong=true">icon</button>
        """
    )

    with pytest.raises(RuntimeError, match="send button did not become enabled"):
        await driver.click_send_button(timeout=0.2)

    assert await page.evaluate("Boolean(window.wrong)") is False


@pytest.mark.asyncio
async def test_send_scopes_generic_submit_fallback_to_composer_form(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <form onsubmit="event.preventDefault(); window.wrong=true">
          <button type="submit">Continue</button>
        </form>
        <form onsubmit="event.preventDefault(); window.sent=true">
          <textarea aria-label="Message ChatGPT">hello</textarea>
          <button type="submit">Go</button>
        </form>
        """
    )

    await driver.click_send_button(timeout=0.2)

    assert await page.evaluate("Boolean(window.sent)") is True
    assert await page.evaluate("Boolean(window.wrong)") is False


@pytest.mark.asyncio
async def test_send_scopes_generic_submit_fallback_to_non_form_composer_wrapper(
    live_driver,
) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <form onsubmit="event.preventDefault(); window.wrong=true">
          <button type="submit">Continue</button>
        </form>
        <section>
          <div>
            <textarea aria-label="Message ChatGPT">hello</textarea>
            <button type="submit" onclick="window.sent=true">Go</button>
          </div>
        </section>
        """
    )

    await driver.click_send_button(timeout=0.2)

    assert await page.evaluate("Boolean(window.sent)") is True
    assert await page.evaluate("Boolean(window.wrong)") is False


@pytest.mark.asyncio
async def test_send_rejects_generic_submit_from_broad_multi_editor_wrapper(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <main>
          <textarea aria-label="Search">query</textarea>
          <textarea aria-label="Message ChatGPT">hello</textarea>
          <button type="submit" onclick="window.wrong=true">Continue</button>
        </main>
        """
    )

    with pytest.raises(RuntimeError, match="send button did not become enabled"):
        await driver.click_send_button(timeout=0.2)

    assert await page.evaluate("Boolean(window.wrong)") is False


@pytest.mark.asyncio
async def test_send_does_not_use_unscoped_generic_submit(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT">hello</textarea>
        <form onsubmit="event.preventDefault(); window.wrong=true">
          <button type="submit">Continue</button>
        </form>
        """
    )

    with pytest.raises(RuntimeError, match="send button did not become enabled"):
        await driver.click_send_button(timeout=0.2)

    assert await page.evaluate("Boolean(window.wrong)") is False


@pytest.mark.asyncio
async def test_stop_prefers_button_accessible_name(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        '<button aria-label="Stop generating" onclick="window.stopped=true">square</button>'
    )

    assert await driver.click_stop(driver.context, timeout=0.2) is True
    assert await page.evaluate("window.stopped") is True


@pytest.mark.asyncio
async def test_stop_survives_role_and_tag_churn_with_labelledby(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <span id="stop-label" hidden>Stop generating</span>
        <div tabindex="0" aria-labelledby="stop-label"
             onclick="window.stopped=true">square</div>
        """
    )

    assert await driver.click_stop(driver.context, timeout=0.2) is True
    assert await page.evaluate("Boolean(window.stopped)") is True


@pytest.mark.asyncio
async def test_stop_survives_role_and_tag_churn_with_describedby(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <span id="stop-description" hidden>Stop generating</span>
        <div tabindex="0" aria-describedby="stop-description"
             onclick="window.stopped=true">square</div>
        """
    )

    assert await driver.click_stop(driver.context, timeout=0.2) is True
    assert await page.evaluate("Boolean(window.stopped)") is True


@pytest.mark.asyncio
async def test_retry_survives_role_and_tag_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <div>Message delivery timed out. Please try again</div>
        <span tabindex="0" title="Retry" onclick="window.retried=true">again</span>
        """
    )

    assert await driver.click_delivery_retry(driver.context, timeout=0.2) is True
    assert await page.evaluate("Boolean(window.retried)") is True


@pytest.mark.asyncio
async def test_stop_ignores_unlabeled_test_id_button(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        '<button data-testid="stop-button" onclick="window.wrong=true">square</button>'
    )

    assert await driver.click_stop(driver.context, timeout=0.2) is False
    assert await page.evaluate("Boolean(window.wrong)") is False


@pytest.mark.asyncio
async def test_login_required_uses_role_and_accessible_name(live_driver) -> None:
    driver, page = live_driver
    await page.set_content('<nav><a href="/auth/login">Log in</a></nav>')

    assert await driver.login_required() is True


@pytest.mark.asyncio
async def test_login_required_survives_private_test_id_and_link_copy_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        '<nav><a data-testid="totally-new-auth-control" href="/auth/login?next=/">Continue</a></nav>'
    )

    assert await driver.login_required() is True


@pytest.mark.asyncio
async def test_login_required_survives_role_and_tag_churn_without_href(live_driver) -> None:
    driver, page = live_driver
    await page.set_content('<div tabindex="0" aria-label="Sign in">Continue</div>')

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
async def test_dom_state_reads_current_search_unit_user_message(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <div data-chatgpt-search-unit-key="fallback-turn-0:1:user"
             data-chatgpt-search-message-ids="u-current">
          <div>Current semantic prompt</div>
        </div>
        """
    )

    state = await driver.dom_state()

    assert state["last_user_id"] == "u-current"
    assert state["last_user_text"] == "Current semantic prompt"


@pytest.mark.asyncio
async def test_dom_state_excludes_role_churned_controls_from_latest_user_text(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <div data-message-author-role="user" data-message-id="u-controls">
          <span>Keep only this prompt.</span>
          <summary>Show more</summary>
          <div tabindex="0" aria-label="Edit message">Edit</div>
          <div role="menuitem">Copy prompt</div>
        </div>
        """
    )

    state = await driver.dom_state()

    assert state["last_user_id"] == "u-controls"
    assert state["last_user_text"] == "Keep only this prompt."


@pytest.mark.asyncio
async def test_dom_state_reads_user_after_semantic_attribute_namespace_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <div data-future-search-unit-key="turn:17:user:content"
             data-future-search-message-ids="u-future">
          <div data-future-selection-message-id="u-future">Prompt after namespace churn</div>
        </div>
        """
    )

    state = await driver.dom_state()

    assert state["last_user_id"] == "u-future"
    assert state["last_user_text"] == "Prompt after namespace churn"


@pytest.mark.asyncio
async def test_dom_state_reads_descendant_message_id_after_attribute_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <main>
          <section>
            <h5>You said:</h5>
            <div data-future-selection-message-id="u-descendant">
              Prompt with descendant-only identity
            </div>
          </section>
          <section>
            <h5>ChatGPT said:</h5>
            <div data-future-selection-message-id="a-descendant">Answer</div>
          </section>
        </main>
        """
    )

    state = await driver.dom_state()

    assert state["last_user_id"] == "u-descendant"
    assert state["last_user_text"] == "Prompt with descendant-only identity"


@pytest.mark.asyncio
async def test_dom_state_ignores_hidden_stale_user_duplicate(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <div data-message-author-role="user" data-message-id="u-visible">Current prompt</div>
        <div style="display:none" data-message-author-role="user" data-message-id="u-stale">
          Hidden stale prompt
        </div>
        """
    )

    state = await driver.dom_state()

    assert state["last_user_id"] == "u-visible"
    assert state["last_user_text"] == "Current prompt"


@pytest.mark.asyncio
async def test_dom_state_reads_heading_only_user_turn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <article>
          <h5>You said:</h5>
          <div data-message-id="u-heading">Prompt after author metadata disappears</div>
        </article>
        """
    )

    state = await driver.dom_state()

    assert state["last_user_id"] == "u-heading"
    assert state["last_user_text"] == "Prompt after author metadata disappears"


@pytest.mark.asyncio
async def test_dom_state_reads_heading_only_user_turn_after_heading_role_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <article>
          <div aria-level="5">You said:</div>
          <div data-message-id="u-heading-roleless">Prompt after heading role disappears</div>
        </article>
        """
    )

    state = await driver.dom_state()

    assert state["last_user_id"] == "u-heading-roleless"
    assert state["last_user_text"] == "Prompt after heading role disappears"


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
async def test_dom_state_dismisses_rate_limit_when_button_copy_changes(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <div role="dialog">
          <p>Too many requests. Try again later.</p>
          <button onclick="this.closest('[role=dialog]').remove()">Continue</button>
        </div>
        """
    )

    state = await driver.dom_state()

    assert "Too many requests" in state["rate_limit_text"]
    assert await page.get_by_role("dialog").count() == 0


@pytest.mark.asyncio
async def test_dom_state_reads_alertdialog_rate_limit_after_role_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <section role="alertdialog">
          <p>Too many requests. Try again later.</p>
          <button onclick="this.closest('[role=alertdialog]').remove()">Close</button>
        </section>
        """
    )

    state = await driver.dom_state()

    assert "Too many requests" in state["rate_limit_text"]
    assert await page.get_by_role("alertdialog").count() == 0


@pytest.mark.asyncio
async def test_dom_state_dismisses_rate_limit_after_control_role_and_tag_churn(
    live_driver,
) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <section role="alertdialog" aria-modal="true">
          <p>Too many requests. Try again later.</p>
          <div tabindex="0" aria-label="Close"
               onclick="this.closest('[role=alertdialog]').remove()">Continue</div>
        </section>
        <textarea aria-label="Message ChatGPT"></textarea>
        """
    )

    state = await driver.dom_state()

    assert "Too many requests" in state["rate_limit_text"]
    assert await page.get_by_role("alertdialog").count() == 0


@pytest.mark.asyncio
async def test_dom_state_recovers_rate_limit_after_modal_semantics_disappear(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <section class="future-overlay-shell">
          <p>Too many requests. Try again later.</p>
          <button onclick="this.closest('section').remove()">Continue</button>
        </section>
        """
    )

    state = await driver.dom_state()

    assert "Too many requests" in state["rate_limit_text"]
    assert await page.locator(".future-overlay-shell").count() == 0


@pytest.mark.asyncio
async def test_dom_state_recovers_rate_limit_after_modal_and_button_semantics_disappear(
    live_driver,
) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <section class="future-overlay-shell">
          <p>Too many requests. Try again later.</p>
          <div tabindex="0" aria-label="Close"
               onclick="this.closest('section').remove()">Continue</div>
        </section>
        """
    )

    state = await driver.dom_state()

    assert "Too many requests" in state["rate_limit_text"]
    assert await page.locator(".future-overlay-shell").count() == 0


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
        <div role="dialog">
          <p>Too many requests while loading conversation history.</p>
          <button onclick="this.closest('[role=dialog]').remove()">Got it</button>
        </div>
        """
    )

    state = await driver.dom_state()

    assert state["rate_limit_text"] == ""
    assert await page.get_by_role("dialog").count() == 0


@pytest.mark.asyncio
async def test_dom_state_dismisses_history_throttling_after_dialog_role_churn(
    live_driver,
) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <section aria-modal="true">
          <p>Too many requests while loading chat history.</p>
          <button onclick="this.closest('[aria-modal=true]').remove()">Dismiss</button>
        </section>
        """
    )

    state = await driver.dom_state()

    assert state["rate_limit_text"] == ""
    assert await page.locator('[aria-modal="true"]').count() == 0


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
async def test_attachment_prefers_hidden_file_input_in_composer_form(
    live_driver,
    tmp_path: Path,
) -> None:
    driver, page = live_driver
    attachment = tmp_path / "scoped.txt"
    attachment.write_text("hello")
    await page.set_content(
        """
        <input id="unrelated" type="file" style="display:none">
        <form>
          <textarea aria-label="Message ChatGPT"></textarea>
          <input id="composer-upload" type="file" style="display:none">
        </form>
        """
    )

    await driver.attach_files([str(attachment)])

    assert await page.locator("#unrelated").evaluate("input => input.files.length") == 0
    assert (
        await page.locator("#composer-upload").evaluate("input => input.files[0].name")
        == "scoped.txt"
    )


@pytest.mark.asyncio
async def test_attachment_prefers_file_input_in_non_form_composer_wrapper(
    live_driver,
    tmp_path: Path,
) -> None:
    driver, page = live_driver
    attachment = tmp_path / "wrapper.txt"
    attachment.write_text("hello")
    await page.set_content(
        """
        <input id="unrelated" type="file" style="display:none">
        <section data-shell="composer">
          <textarea aria-label="Message ChatGPT"></textarea>
          <input id="composer-upload" type="file" style="display:none">
        </section>
        """
    )

    await driver.attach_files([str(attachment)])

    assert await page.locator("#unrelated").evaluate("input => input.files.length") == 0
    assert (
        await page.locator("#composer-upload").evaluate("input => input.files[0].name")
        == "wrapper.txt"
    )


@pytest.mark.asyncio
async def test_attachment_prefers_unique_multi_file_input_inside_composer(
    live_driver,
    tmp_path: Path,
) -> None:
    driver, page = live_driver
    attachment = tmp_path / "ranked.txt"
    attachment.write_text("hello")
    await page.set_content(
        """
        <form>
          <textarea aria-label="Message ChatGPT"></textarea>
          <input id="media-upload" type="file" accept="image/*" style="display:none">
          <input id="general-upload" type="file" multiple style="display:none">
        </form>
        """
    )

    await driver.attach_files([str(attachment)])

    assert await page.locator("#media-upload").evaluate("input => input.files.length") == 0
    assert (
        await page.locator("#general-upload").evaluate("input => input.files[0].name")
        == "ranked.txt"
    )


@pytest.mark.asyncio
async def test_attachment_rejects_ambiguous_page_wide_file_inputs(
    live_driver,
    tmp_path: Path,
) -> None:
    driver, page = live_driver
    attachment = tmp_path / "ambiguous.txt"
    attachment.write_text("hello")
    await page.set_content(
        """
        <textarea aria-label="Message ChatGPT"></textarea>
        <input type="file" style="display:none">
        <input type="file" style="display:none">
        """
    )

    with pytest.raises(RuntimeError, match="attachment input could not be found"):
        await driver.attach_files([str(attachment)])


@pytest.mark.asyncio
async def test_ensure_chat_surface_dismisses_history_rate_limit_modal(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <div role="dialog" data-testid="modal-conversation-history-rate-limit">
          <p>Too many requests. Please wait a few minutes before trying again.</p>
          <button onclick="this.closest('[role=dialog]').remove()">Got it</button>
        </div>
        <button role="radio" aria-checked="true">Chat</button>
        <button role="radio" aria-checked="false">Work</button>
        """
    )

    await driver.ensure_chat_surface(timeout=0.5)

    assert await page.get_by_role("dialog").count() == 0
    assert await driver.dismiss_history_rate_limit() is True
    assert await driver.dismiss_history_rate_limit() is False


@pytest.mark.asyncio
async def test_history_rate_limit_dismiss_survives_button_copy_change(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <section role="alertdialog" aria-modal="true">
          <p>Too many requests while loading your conversation history.</p>
          <button onclick="this.closest('[role=alertdialog]').remove()">Continue</button>
        </section>
        <textarea aria-label="Message ChatGPT"></textarea>
        """
    )

    assert await driver.dismiss_history_rate_limit() is True
    assert await page.get_by_role("alertdialog").count() == 0


@pytest.mark.asyncio
async def test_history_rate_limit_dismiss_survives_modal_role_and_testid_removal(
    live_driver,
) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <section class="future-history-overlay">
          <p>Too many requests while loading your conversation history.</p>
          <button onclick="this.closest('section').remove()">Continue</button>
        </section>
        <textarea aria-label="Message ChatGPT"></textarea>
        """
    )

    assert await driver.dismiss_history_rate_limit() is True
    assert await page.locator(".future-history-overlay").count() == 0


@pytest.mark.asyncio
async def test_history_rate_limit_dismiss_survives_modal_and_button_semantics_removal(
    live_driver,
) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <section class="future-history-overlay">
          <p>Too many requests while loading your conversation history.</p>
          <span tabindex="0" title="Dismiss"
                onclick="this.closest('section').remove()">Continue</span>
        </section>
        <textarea aria-label="Message ChatGPT"></textarea>
        """
    )

    assert await driver.dismiss_history_rate_limit() is True
    assert await page.locator(".future-history-overlay").count() == 0


@pytest.mark.asyncio
async def test_ensure_chat_surface_selects_chat_radio(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <button id="chat" role="radio" aria-checked="false"
                onclick="this.setAttribute('aria-checked','true');
                         document.getElementById('work').setAttribute('aria-checked','false')">
          Chat
        </button>
        <button id="work" role="radio" aria-checked="true">Work</button>
        """
    )

    await driver.ensure_chat_surface()

    assert await page.locator("#chat").get_attribute("aria-checked") == "true"
    assert await page.locator("#work").get_attribute("aria-checked") == "false"


@pytest.mark.asyncio
async def test_ensure_chat_surface_survives_tab_role_and_selected_state_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <button id="chat" role="tab" aria-selected="false"
                onclick="this.setAttribute('aria-selected','true');
                         document.getElementById('work').setAttribute('aria-selected','false')">
          Chat mode
        </button>
        <button id="work" role="tab" aria-selected="true">Work</button>
        """
    )

    await driver.ensure_chat_surface(timeout=0.5)

    assert await page.locator("#chat").get_attribute("aria-selected") == "true"
    assert await page.locator("#work").get_attribute("aria-selected") == "false"


@pytest.mark.asyncio
async def test_ensure_chat_surface_survives_missing_accessible_role(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <button id="chat" data-state="inactive"
                onclick="this.dataset.state='active';
                         document.getElementById('composer').hidden=false">
          Chat
        </button>
        <textarea id="composer" aria-label="Ask ChatGPT" hidden></textarea>
        """
    )

    await driver.ensure_chat_surface(timeout=0.5)

    assert await page.locator("#chat").get_attribute("data-state") == "active"
    assert await page.locator("#composer").is_visible()


@pytest.mark.asyncio
async def test_ensure_chat_surface_survives_role_and_tag_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <main>
          <div id="chat" tabindex="0" aria-label="Chat mode" data-state="inactive"
               onclick="this.dataset.state='active';
                        document.getElementById('composer').hidden=false">
            Open
          </div>
          <textarea id="composer" aria-label="Ask ChatGPT" hidden></textarea>
        </main>
        """
    )

    await driver.ensure_chat_surface(timeout=0.5)

    assert await page.locator("#chat").get_attribute("data-state") == "active"
    assert await page.locator("#composer").is_visible()


@pytest.mark.asyncio
async def test_ensure_chat_surface_accepts_composer_without_mode_radio(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        '<textarea aria-label="Chat with ChatGPT" placeholder="Ask ChatGPT"></textarea>'
    )

    await driver.ensure_chat_surface(timeout=0.2)


@pytest.mark.asyncio
async def test_effort_trigger_accepts_thinking_effort_button(live_driver) -> None:
    driver, page = live_driver
    await page.set_content('<button aria-haspopup="menu">Thinking effort</button>')

    trigger = await driver.effort_trigger_info(timeout=0.2)

    assert trigger["text"] == "Thinking effort"
    assert trigger["label"] == "Thinking effort"
    assert trigger["x"] > 0
    assert trigger["y"] > 0


@pytest.mark.asyncio
async def test_effort_trigger_accepts_model_label_with_effort_text(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        '<button aria-label="Select ChatGPT model" aria-haspopup="menu">Medium</button>'
    )

    trigger = await driver.effort_trigger_info(timeout=0.2)

    assert trigger["text"] == "Medium"
    assert "Select ChatGPT model" in trigger["label"]


@pytest.mark.asyncio
async def test_effort_trigger_accepts_combobox_role_after_role_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        '<div role="combobox" aria-label="Thinking effort" aria-haspopup="listbox" '
        'tabindex="0">High</div>'
    )

    trigger = await driver.effort_trigger_info(timeout=0.2)

    assert trigger["text"] == "High"
    assert "Thinking effort" in trigger["label"]


@pytest.mark.asyncio
async def test_effort_trigger_accepts_popup_owner_without_role(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        '<div aria-label="Select ChatGPT model" aria-haspopup="menu" tabindex="0">Medium</div>'
    )

    trigger = await driver.effort_trigger_info(timeout=0.2)

    assert trigger["text"] == "Medium"


@pytest.mark.asyncio
async def test_effort_trigger_accepts_roleless_popup_owner_with_describedby(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <span id="effort-description" hidden>Thinking effort</span>
        <div aria-describedby="effort-description" aria-haspopup="menu"
             tabindex="0">Adaptive</div>
        """
    )

    trigger = await driver.effort_trigger_info(timeout=0.2)

    assert trigger["text"] == "Thinking effort"
    assert "Thinking effort" in trigger["label"]


@pytest.mark.asyncio
async def test_select_effort_model_uses_direct_chat_menu_item(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <div id="sol" role="menuitemradio" aria-label="GPT-5.6 Sol"
             onclick="this.dataset.clicked='true'">GPT-5.6 Sol</div>
        """
    )

    await driver.select_effort_model()

    assert await page.locator("#sol").get_attribute("data-clicked") == "true"


@pytest.mark.asyncio
async def test_select_effort_model_uses_unique_structural_submenu_when_copy_changes(
    live_driver,
) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <div id="selector" role="menuitem" aria-label="Choose engine" aria-haspopup="menu"
             onclick="document.getElementById('models').hidden=false">Choose engine</div>
        <div id="models" hidden>
          <div id="sol" role="menuitemradio" aria-label="GPT-5.6 Sol"
               onclick="this.dataset.clicked='true'">GPT-5.6 Sol</div>
        </div>
        """
    )

    await driver.select_effort_model()

    assert await page.locator("#sol").get_attribute("data-clicked") == "true"


@pytest.mark.asyncio
async def test_select_effort_model_accepts_radio_role_after_menu_role_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <div id="sol" role="radio" aria-label="GPT-5.6 Sol"
             onclick="this.dataset.clicked='true'">GPT-5.6 Sol</div>
        """
    )

    await driver.select_effort_model()

    assert await page.locator("#sol").get_attribute("data-clicked") == "true"


@pytest.mark.asyncio
async def test_select_effort_model_accepts_combobox_submenu_after_role_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <div id="selector" role="combobox" aria-haspopup="listbox" tabindex="0"
             onclick="document.getElementById('models').hidden=false">Choose engine</div>
        <div id="models" hidden>
          <div id="sol" role="option" aria-label="GPT-5.6 Sol"
               onclick="this.dataset.clicked='true'">GPT-5.6 Sol</div>
        </div>
        """
    )

    await driver.select_effort_model()

    assert await page.locator("#sol").get_attribute("data-clicked") == "true"


@pytest.mark.asyncio
async def test_select_effort_model_accepts_button_submenu_after_role_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <button id="selector" aria-haspopup="menu"
                onclick="document.getElementById('models').hidden=false">Choose engine</button>
        <div id="models" hidden>
          <div id="sol" role="radio" aria-label="GPT-5.6 Sol"
               onclick="this.dataset.clicked='true'">GPT-5.6 Sol</div>
        </div>
        """
    )

    await driver.select_effort_model()

    assert await page.locator("#sol").get_attribute("data-clicked") == "true"


@pytest.mark.asyncio
async def test_select_effort_model_accepts_already_checked_model(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <div id="sol" role="menuitemradio" aria-label="GPT-5.6 Sol"
             aria-checked="true" onclick="this.dataset.clicked='true'">GPT-5.6 Sol</div>
        """
    )

    await driver.select_effort_model()

    assert await page.locator("#sol").get_attribute("data-clicked") is None


@pytest.mark.asyncio
async def test_power_control_survives_selectable_role_churn(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <div id="power" role="button" aria-label="Reasoning intensity" tabindex="0">
          Reasoning intensity
          <span role="slider" aria-valuemin="0" aria-valuemax="3"
                aria-valuenow="1" aria-hidden="true"></span>
        </div>
        """
    )

    power = await driver._power_control(page)

    assert power is not None
    assert await power.get_attribute("id") == "power"


@pytest.mark.asyncio
async def test_power_control_survives_wrapper_role_removal(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <div id="power" tabindex="0">
          <span>Reasoning intensity</span>
          <span role="slider" aria-valuemin="0" aria-valuemax="3"
                aria-valuenow="1" aria-hidden="true"></span>
        </div>
        """
    )

    power = await driver._power_control(page)

    assert power is not None
    assert await power.get_attribute("id") == "power"


@pytest.mark.asyncio
async def test_effort_power_info_survives_slider_role_removal(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <span id="power-state">Medium, 2 of 4.</span>
        <div id="power" tabindex="0" aria-describedby="power-state">
          <span>Reasoning intensity</span>
          <span aria-valuemin="0" aria-valuemax="3" aria-valuenow="1"
                aria-hidden="true"></span>
        </div>
        """
    )

    info = await driver.effort_power_info()

    assert info["text"] == "Medium"
    assert info["position"] == 2
    assert info["total"] == 4
    assert info["value"] == 1


@pytest.mark.asyncio
async def test_set_effort_power_position_survives_slider_role_removal(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <button aria-haspopup="menu" onclick="document.getElementById('menu').hidden=false">
          Thinking effort
        </button>
        <div id="menu" hidden>
          <span id="power-state">Medium, 2 of 4.</span>
          <div id="power" tabindex="0" aria-describedby="power-state"
               onkeydown="
                 const labels = ['Instant', 'Medium', 'High', 'Pro'];
                 const slider = this.querySelector('[aria-valuenow][aria-valuemin][aria-valuemax]');
                 let value = Number(slider.getAttribute('aria-valuenow'));
                 if (event.key === 'ArrowRight') value = Math.min(3, value + 1);
                 if (event.key === 'ArrowLeft') value = Math.max(0, value - 1);
                 slider.setAttribute('aria-valuenow', String(value));
                 document.getElementById('power-state').textContent =
                   labels[value] + ', ' + (value + 1) + ' of 4.';
               ">
            <span>Reasoning intensity</span>
            <span aria-valuemin="0" aria-valuemax="3" aria-valuenow="1"
                  aria-hidden="true"></span>
          </div>
        </div>
        """
    )

    info = await driver.set_effort_power_position(3)

    assert info["text"] == "High"
    assert info["position"] == 3
    assert info["value"] == 2


@pytest.mark.asyncio
async def test_set_effort_power_position_targets_high_not_locked_pro(live_driver) -> None:
    driver, page = live_driver
    await page.set_content(
        """
        <button aria-haspopup="menu" onclick="document.getElementById('menu').hidden=false">
          Thinking effort
        </button>
        <div id="menu" hidden>
          <span id="power-state">Medium, 2 of 4.</span>
          <span id="power-help">Use Left and Right arrow keys to adjust power.</span>
          <div id="power" role="menuitem" aria-label="Reasoning intensity" tabindex="0"
               aria-describedby="power-state power-help"
               onkeydown="
                 const labels = ['Instant', 'Medium', 'High', 'Pro'];
                 const slider = this.querySelector('[role=slider]');
                 let value = Number(slider.getAttribute('aria-valuenow'));
                 if (event.key === 'ArrowRight') value = Math.min(3, value + 1);
                 if (event.key === 'ArrowLeft') value = Math.max(0, value - 1);
                 slider.setAttribute('aria-valuenow', String(value));
                 document.getElementById('power-state').textContent =
                   labels[value] + ', ' + (value + 1) + ' of 4.';
               ">
            Reasoning intensity
            <span role="slider" aria-valuemin="0" aria-valuemax="3"
                  aria-valuenow="1" aria-hidden="true"></span>
          </div>
        </div>
        """
    )

    info = await driver.set_effort_power_position(3)

    assert info["text"] == "High"
    assert info["position"] == 3
    assert info["value"] == 2
    assert "Upgrade required" not in info["description"]


@pytest.mark.asyncio
async def test_new_tab_navigates_directly_without_clicking_new_chat_ui(live_driver) -> None:
    driver, page = live_driver
    context = driver._browser_context
    assert context is not None

    async def fulfill(route):
        await route.fulfill(
            status=200,
            content_type="text/html",
            body=(
                "<script>window.name = ''</script>"
                '<a role="link" aria-label="New chat">New chat</a><main>fresh</main>'
            ),
        )

    await context.route("https://chatgpt.com/**", fulfill)

    context_id = await driver.new_tab()

    new_page = driver._pages[context_id]
    assert new_page.url == "https://chatgpt.com/"
    assert await new_page.get_by_text("fresh").count() == 1
    assert (await new_page.evaluate("window.name")).startswith("prompta:")


def test_connect_does_not_depend_on_new_chat_sidebar_click() -> None:
    source = inspect.getsource(PlaywrightDriver.connect)

    assert 'self.navigate("https://chatgpt.com/"' in source
    assert "new_chat.click" not in source


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
async def test_history_navigation_survives_accessible_role_churn(live_driver) -> None:
    driver, page = live_driver

    async def fulfill(route):
        await route.fulfill(status=200, content_type="text/html", body="<main>target</main>")

    await page.route("https://chatgpt.com/**", fulfill)
    await page.set_content('<a role="button" href="https://chatgpt.com/c/target">History item</a>')

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
    await owned_page.evaluate(
        "(value) => { window.name = value; }",
        f"prompta:1:{driver.page_owner_id}:test",
    )

    context_id = await driver.find_context_for_path("/c/owned")

    assert context_id
    assert driver._pages[context_id] is owned_page


@pytest.mark.asyncio
async def test_handoff_context_keeps_page_open_for_tracker_claim(
    live_driver,
    tmp_path: Path,
) -> None:
    driver, _page = live_driver
    context = driver._browser_context
    assert context is not None

    async def fulfill(route):
        await route.fulfill(status=200, content_type="text/html", body="<main>chat</main>")

    await context.route("https://chatgpt.com/**", fulfill)
    delivery_context = await driver.new_tab("https://chatgpt.com/c/handoff")
    delivery_page = driver._pages[delivery_context]

    await driver.handoff_context(
        delivery_context,
        ownership_prefix="prompta-conversation:",
    )

    assert delivery_context not in driver._owned_contexts
    assert not delivery_page.is_closed()
    marker = await delivery_page.evaluate("window.name")
    assert marker.startswith("prompta-conversation:")
    assert ":handoff:" in marker

    tracker = PlaywrightDriver(
        profile=tmp_path / "tracker-profile",
        ownership_prefix="prompta-conversation:",
    )
    tracker._browser = driver._browser
    tracker._browser_context = context
    tracker._connected = True

    claimed_context = await tracker.find_context_for_path("/c/handoff")

    assert claimed_context
    assert tracker._pages[claimed_context] is delivery_page
    claimed_marker = await delivery_page.evaluate("window.name")
    assert f":{tracker.page_owner_id}:" in claimed_marker


@pytest.mark.asyncio
async def test_find_context_for_path_prefers_fresh_handoff_over_registered_duplicate(
    live_driver,
    tmp_path: Path,
) -> None:
    driver, _page = live_driver
    context = driver._browser_context
    assert context is not None

    async def fulfill(route):
        await route.fulfill(status=200, content_type="text/html", body="<main>chat</main>")

    await context.route("https://chatgpt.com/**", fulfill)

    tracker = PlaywrightDriver(
        profile=tmp_path / "tracker-profile",
        ownership_prefix="prompta-conversation:",
    )
    tracker._browser = driver._browser
    tracker._browser_context = context
    tracker._connected = True

    stale_page = await context.new_page()
    await stale_page.goto("https://chatgpt.com/c/duplicate")
    await tracker._mark_owned(stale_page)
    stale_context = tracker._register_page(stale_page, owned=True)

    delivery_context = await driver.new_tab("https://chatgpt.com/c/duplicate")
    delivery_page = driver._pages[delivery_context]
    await driver.handoff_context(
        delivery_context,
        ownership_prefix="prompta-conversation:",
    )

    claimed_context = await tracker.find_context_for_path("/c/duplicate")

    assert claimed_context
    assert claimed_context != stale_context
    assert tracker._pages[claimed_context] is delivery_page
    claimed_marker = await delivery_page.evaluate("window.name")
    assert f":{tracker.page_owner_id}:" in claimed_marker


@pytest.mark.asyncio
async def test_orphan_cleanup_reaps_only_stale_unregistered_prompta_pages(live_driver) -> None:
    driver, page = live_driver
    context = driver._browser_context
    assert context is not None

    stale_orphan = await context.new_page()
    await stale_orphan.evaluate("window.name='prompta:1:99999999-dead:stale'")
    stale_handoff = await context.new_page()
    await stale_handoff.evaluate("window.name='prompta:1:handoff:stale'")
    pending_handoff = await context.new_page()
    await pending_handoff.evaluate(
        "(stamp) => { window.name = 'prompta:' + stamp + ':handoff:pending'; }",
        int(time.time()) - 120,
    )
    recent_orphan = await context.new_page()
    await recent_orphan.evaluate(
        "(stamp) => { window.name = 'prompta:' + stamp + ':99999999-dead:recent'; }",
        int(time.time()),
    )
    live_peer = await context.new_page()
    await live_peer.evaluate("window.name='prompta:1:12345-live:peer'")
    unrelated = await context.new_page()
    await unrelated.evaluate("window.name='user-owned'")

    with patch(
        "prompta.playwright_driver.owned_window_owner_alive",
        side_effect=lambda owner: owner == "12345-live",
    ):
        closed = await driver.cleanup_orphan_pages(
            minimum_age_seconds=60,
            interval_seconds=1,
        )

    assert closed == 2
    assert stale_orphan.is_closed()
    assert stale_handoff.is_closed()
    assert not pending_handoff.is_closed()
    assert not recent_orphan.is_closed()
    assert not live_peer.is_closed()
    assert not unrelated.is_closed()
    assert not page.is_closed()


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


def test_semantic_locators_are_first_in_browser_controls() -> None:
    composer_source = inspect.getsource(PlaywrightDriver._composer)
    button_source = inspect.getsource(PlaywrightDriver._semantic_button)
    effort_trigger_source = inspect.getsource(PlaywrightDriver._effort_trigger_locator)
    login_source = inspect.getsource(PlaywrightDriver.login_required)
    model_source = inspect.getsource(PlaywrightDriver.select_effort_model)
    power_source = inspect.getsource(PlaywrightDriver.effort_power_info)

    assert 'get_by_role("textbox"' in composer_source
    assert "locator(selector)" not in composer_source
    assert "get_by_role(role, name=name)" in button_source
    assert "semantic_control_labels.js" in button_source
    assert "get_by_test_id" not in button_source
    assert "data-testid" not in button_source
    assert "get_by_role(role, name=name)" in effort_trigger_source
    assert 'page.locator("[aria-haspopup]")' in effort_trigger_source
    assert "get_by_test_id" not in login_source
    assert '[href*="/login" i]' in login_source
    assert 'for role in ("menuitemradio", "radio", "option")' in model_source
    assert 'get_by_role("slider", include_hidden=True)' in power_source
    assert "locator('[role=\"slider\"]')" not in power_source
