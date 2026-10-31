"""Exercise the read-only recovery probe against a real browser DOM fixture."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

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
                result = await page.evaluate(script)
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
                mismatched = await page.evaluate(script)
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
      <div data-content-search-unit-key="fallback-turn-0:0:user">Original prompt</div>
      <article>
        <div data-content-search-unit-key="fallback-turn-0:1:assistant" data-content-search-message-ids="{first}">
          <div class="markdown">First chunk</div></div>
        <button data-state="completed">Used Search</button>
      </article>
      <article>
        <div data-content-search-unit-key="fallback-turn-0:2:assistant" data-content-search-message-ids="{final} {final}">
          <div class="markdown">Final chunk</div></div>
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
                result = await page.evaluate(script)
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
