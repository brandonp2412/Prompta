"""Exercise the read-only recovery probe against a real browser DOM fixture."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from patchright.async_api import async_playwright

from prompta.browser_script_loader import load_browser_script

CONVERSATION = "12345678-1234-4123-8123-123456789abc"
PROMPT = "Original prompt"
HTML = """<html><body><main>
<article><div data-message-author-role="user"><p>Original prompt</p></div></article>
<article><div data-message-author-role="assistant"
  data-message-id="87654321-4321-4321-8321-123456789abc">
  <div class="markdown"><p>Recovered <strong>answer</strong></p><ul><li>First</li><li>Second</li></ul><table><tr><th>State</th><th>Count</th></tr><tr><td>Done</td><td>3</td></tr></table></div></div>
  <button data-testid="tool-call-entry" aria-label="Used Nox Python" data-state="completed">Tool</button>
  <button data-state="completed">Used Calendar</button>
  <button data-testid="copy-turn-action-button">Copy</button>
</article></main></body></html>"""


def test_historical_probe_real_chromium_dom() -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.exists():
        pytest.skip("Chromium test browser is not installed")
    source = load_browser_script("historical_response_probe.js")
    script = source.replace("__CONVERSATION__", json.dumps(CONVERSATION)).replace(
        "__ORIGINAL_PROMPT__",
        json.dumps(PROMPT),
    )

    async def fixture() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path=str(chromium),
                headless=True,
            )
            try:
                page = await browser.new_page()
                # Only a synthetic HTML fixture is served; no live ChatGPT request.
                await page.route(
                    "https://chatgpt.com/c/**",
                    lambda route: route.fulfill(status=200, content_type="text/html", body=HTML),
                )
                await page.goto("https://chatgpt.com/c/" + CONVERSATION)
                result = await page.evaluate(script, isolated_context=False)
                assert isinstance(result, dict)
                assert result["verified"] is True
                assert result["complete"] is True
                assert (
                    result["text"]
                    == "Recovered **answer**\n\n- First\n- Second\n\n| State | Count |\n| --- | --- |\n| Done | 3 |"
                )
                assert result["tool_calls"] == [
                    {"action": "Used Nox Python", "status": "completed"},
                    {"action": "Used Calendar", "status": "completed"},
                ]
                assert result["branch_message_id"] == "87654321-4321-4321-8321-123456789abc"
                await page.locator('[data-message-author-role="user"] p').evaluate(
                    "element => element.textContent = 'Wrong prompt'",
                )
                mismatched = await page.evaluate(script, isolated_context=False)
                assert isinstance(mismatched, dict)
                assert mismatched["ambiguous"] is True
                assert mismatched["text"] == ""
            finally:
                await browser.close()

    asyncio.run(fixture())


def test_historical_tools_follow_all_chunks_of_only_the_original_turn() -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.exists():
        pytest.skip("Chromium test browser is not installed")
    script = load_browser_script("historical_response_probe.js").replace(
        "__CONVERSATION__", json.dumps(CONVERSATION),
    ).replace("__ORIGINAL_PROMPT__", json.dumps(PROMPT))
    first = "11111111-1111-4111-8111-111111111111"
    final = "22222222-2222-4222-8222-222222222222"
    html = f"""<main>
      <div data-content-search-unit-key="fallback-turn-0:0:user">
        <h2>You said:</h2><div data-message-author-role="user"><div class="whitespace-pre-wrap">Original prompt</div></div>
      </div>
      <article>
        <div data-content-search-unit-key="fallback-turn-0:1:assistant" data-content-search-message-ids="{first}">
          <div data-message-author-role="assistant" data-message-id="{first}"><div class="markdown">First chunk</div></div></div>
        <button data-state="completed">Used Search</button>
      </article>
      <article>
        <div data-content-search-unit-key="fallback-turn-0:2:assistant" data-content-search-message-ids="{first} {final}">
          <div data-message-author-role="assistant" data-message-id="{final}"><div class="markdown">Final chunk</div></div></div>
        <button data-state="completed">Used Calendar</button>
        <button data-testid="copy-turn-action-button">Copy</button>
      </article>
      <div data-content-search-unit-key="fallback-turn-1:0:user">Later follow up</div>
      <article>
        <div data-content-search-unit-key="fallback-turn-1:1:assistant"><div class="markdown">Later answer</div></div>
        <button>Used Unrelated App</button>
      </article>
    </main>"""

    async def fixture() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path=str(chromium), headless=True)
            try:
                page = await browser.new_page()
                await page.route("https://chatgpt.com/c/**", lambda route: route.fulfill(
                    status=200, content_type="text/html", body=html,
                ))
                await page.goto("https://chatgpt.com/c/" + CONVERSATION)
                result = await page.evaluate(script, isolated_context=False)
                assert result["verified"] is True and result["complete"] is True
                assert result["text"] == "First chunk\n\nFinal chunk"
                assert result["branch_message_id"] == final
                assert result["tool_calls"] == [
                    {"action": "Used Search", "status": "completed"},
                    {"action": "Used Calendar", "status": "completed"},
                ]
            finally:
                await browser.close()

    asyncio.run(fixture())


def test_live_capture_deduplicates_nested_messages_and_keeps_tool_headings() -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.exists():
        pytest.skip("Chromium test browser is not installed")
    first = "11111111-1111-4111-8111-111111111111"
    final = "22222222-2222-4222-8222-222222222222"
    response = f"""<article>
      <div data-content-search-unit-key="fallback-turn-0:1:assistant" data-content-search-message-ids="{first}">
        <div data-message-author-role="assistant" data-message-id="{first}"><div class="markdown">First chunk</div></div>
      </div><button data-state="completed">Used Search</button>
    </article><article>
      <div data-content-search-unit-key="fallback-turn-0:2:assistant" data-content-search-message-ids="{first} {final}">
        <div data-message-author-role="assistant" data-message-id="{final}"><div class="markdown">Final chunk</div></div>
      </div><div>private reasoning</div><button data-state="completed">Used Calendar</button>
      <button data-testid="copy-turn-action-button">Copy</button>
    </article>"""

    async def fixture() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path=str(chromium), headless=True)
            try:
                page = await browser.new_page()
                await page.route("https://chatgpt.com/c/**", lambda route: route.fulfill(
                    status=200, content_type="text/html", body="<main></main>",
                ))
                await page.goto("https://chatgpt.com/c/" + CONVERSATION)
                assert await page.evaluate(load_browser_script("passive_response_observer.js"), isolated_context=False)
                await page.evaluate("""html => {
                    const fixture = new DOMParser().parseFromString(html, 'text/html');
                    document.querySelector('main').append(...fixture.body.childNodes);
                }""", response, isolated_context=False)
                await page.wait_for_function("window.__promptaPassiveResponseObserver.read().complete")
                captured = await page.evaluate(load_browser_script("passive_response_read.js"), isolated_context=False)
                assert captured["ambiguous"] is False
                assert captured["text"] == "First chunk\n\nFinal chunk"
                assert captured["branch_message_id"] == final
                assert captured["tool_calls"] == [
                    {"action": "Used Search", "status": "completed"},
                    {"action": "Used Calendar", "status": "completed"},
                ]
                assert "private reasoning" not in str(captured)
            finally:
                await browser.close()

    asyncio.run(fixture())


@pytest.mark.asyncio
async def test_patchright_passive_observer_uses_main_world_for_exposed_callbacks() -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium test browser is not installed")

    updates: list[object] = []

    def receive(payload: object) -> None:
        updates.append(payload)

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"]
        )
        try:
            page = await browser.new_page()
            await page.set_content("<main></main>")
            await page.expose_function("__promptaPassiveUpdate", receive)
            assert await page.evaluate(
                load_browser_script("passive_response_observer.js"), isolated_context=False
            )
            response = (
                '<article><div data-message-author-role="assistant" data-message-id="fresh">'
                '<div class="markdown">A new answer</div></div>'
                '<button data-testid="copy-turn-action-button">Copy</button></article>'
            )
            await page.locator("main").evaluate(
                "(element, html) => { element.innerHTML = html }", response
            )
            deadline = asyncio.get_running_loop().time() + 4.0
            while asyncio.get_running_loop().time() < deadline:
                if any(
                    isinstance(item, dict)
                    and item.get("text") == "A new answer"
                    and item.get("complete") is True
                    for item in updates
                ):
                    break
                await asyncio.sleep(0.1)
            assert any(
                isinstance(item, dict)
                and item.get("text") == "A new answer"
                and item.get("complete") is True
                for item in updates
            )
            assert await page.evaluate(
                load_browser_script("passive_response_read.js"), isolated_context=False
            )
            await page.evaluate(
                load_browser_script("passive_response_stop.js"), isolated_context=False
            )
        finally:
            await browser.close()
