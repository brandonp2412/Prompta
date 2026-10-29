"""Exercise the read-only recovery probe against a real browser DOM fixture."""
from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

CONVERSATION = "12345678-1234-4123-8123-123456789abc"
PROMPT = "Original prompt"
HTML = """<html><body><main>
<article><div data-message-author-role="user"><p>Original prompt</p></div></article>
<article><div data-message-author-role="assistant"
  data-message-id="87654321-4321-4321-8321-123456789abc">
  <div class="markdown"><p>Recovered <strong>answer</strong></p></div></div>
  <button data-testid="tool-call-entry" aria-label="Used Nox Python" data-state="completed">Tool</button>
  <button data-testid="copy-turn-action-button">Copy</button>
</article></main></body></html>"""


def test_historical_probe_real_chromium_dom() -> None:
    if not Path("/usr/bin/chromium").exists():
        pytest.skip("Nox Chromium is not installed")
    source = Path("src/browser_scripts/historical_response_probe.js").read_text()
    script = source.replace("__CONVERSATION__", json.dumps(CONVERSATION)).replace(
        "__ORIGINAL_PROMPT__", json.dumps(PROMPT),
    )

    async def fixture() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path="/usr/bin/chromium", headless=True,
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
                assert result["text"] == "Recovered answer"
                assert result["tool_calls"] == [{"action": "Used Nox Python", "status": "completed"}]
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
