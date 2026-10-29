"""A real Chromium DOM fixture proves exact-branch read-only reply recovery."""
from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

CONVERSATION = "12345678-1234-4123-8123-123456789abc"
PARENT = "87654321-4321-4321-8321-123456789abc"
ANSWER = "11111111-1111-4111-8111-111111111111"
HTML = f"""<html><body><main>
<article><div data-message-author-role="user">Original prompt</div></article>
<article><div data-message-author-role="assistant" data-message-id="{PARENT}">
 <div class="markdown">Original answer</div></div><button data-testid="copy-turn-action-button">Copy</button></article>
<article><div data-message-author-role="user">Follow up</div></article>
<article><div data-message-author-role="assistant" data-message-id="{ANSWER}">
 <div class="markdown"><p>Recovered follow-up</p></div></div>
 <button data-testid="tool-call-entry" aria-label="Used Nox Python" data-state="completed">Tool</button>
 <button data-testid="copy-turn-action-button">Copy</button></article>
</main></body></html>"""


def test_reply_history_probe_real_chromium_dom() -> None:
    if not Path("/usr/bin/chromium").exists():
        pytest.skip("Nox Chromium is not installed")
    source = Path("src/browser_scripts/historical_reply_probe.js").read_text()
    for forbidden in (r"fetch\s*\(", "XMLHttpRequest", "backend-api", r"window\.open\s*\("):
        assert re.search(forbidden, source) is None
    script = (source.replace("__CONVERSATION__", json.dumps(CONVERSATION))
              .replace("__ORIGINAL_PROMPT__", json.dumps("Original prompt"))
              .replace("__REPLY_TEXT__", json.dumps("Follow up"))
              .replace("__PARENT__", json.dumps(PARENT)))

    async def check() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(
                executable_path="/usr/bin/chromium", headless=True,
            )
            try:
                page = await browser.new_page()
                await page.route("https://chatgpt.com/c/**", lambda route: route.fulfill(
                    status=200, content_type="text/html", body=HTML,
                ))
                await page.goto("https://chatgpt.com/c/" + CONVERSATION)
                result = await page.evaluate(script)
                assert result["verified"] is True and result["complete"] is True
                assert result["verified_parent_id"] == PARENT
                assert result["branch_message_id"] == ANSWER
                assert result["text"] == "Recovered follow-up"
                assert result["tool_calls"] == [{"action": "Used Nox Python", "status": "completed"}]
                await page.locator('[data-message-author-role="user"]').nth(1).evaluate(
                    "element => element.textContent = 'Different reply'",
                )
                mismatch = await page.evaluate(script)
                assert mismatch["ambiguous"] is True and mismatch["text"] == ""
            finally:
                await browser.close()

    asyncio.run(check())
