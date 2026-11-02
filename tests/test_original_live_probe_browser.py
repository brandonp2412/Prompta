"""Browser-backed exact-identity checks for active historical streams."""

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


@pytest.mark.parametrize("with_assistant", [False, True])
def test_exact_original_probe_reports_live_generation(with_assistant: bool) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium test browser is not installed")
    source = load_browser_script("historical_response_probe.js")
    script = source.replace("__CONVERSATION__", json.dumps(CONVERSATION)).replace(
        "__ORIGINAL_PROMPT__", json.dumps(PROMPT),
    )
    assistant = (
        '<article><div data-message-author-role="assistant" '
        'data-message-id="87654321-4321-4321-8321-123456789abc">'
        '<div class="markdown">Partial answer</div></div>'
        '<button data-testid="copy-turn-action-button">Copy</button></article>'
        '<button aria-label="Stop">Stop</button>'
        if with_assistant else
        '<div data-content-search-unit-key="fallback-turn-0:1:assistant">'
        '<div data-talvt-turn-state="in_progress"></div></div>'
        '<button aria-label="Stop">Stop</button>'
    )
    html = (
        '<main><section data-content-search-turn-key="fallback-turn-0">'
        '<div data-content-search-unit-key="fallback-turn-0:0:user">'
        '<div class="whitespace-pre-wrap">Original prompt</div></div>'
        + assistant + '</section></main>'
    )

    async def fixture() -> None:
        async with async_playwright() as patchright:
            browser = await patchright.chromium.launch(
                executable_path=str(chromium), headless=True,
            )
            try:
                page = await browser.new_page()
                await page.route(
                    "https://chatgpt.com/c/**",
                    lambda route: route.fulfill(
                        status=200, content_type="text/html", body=html,
                    ),
                )
                await page.goto("https://chatgpt.com/c/" + CONVERSATION)
                payload = await page.evaluate(script, isolated_context=False)
                assert payload["verified"] is True
                assert payload["generating"] is True
                assert payload["complete"] is False
                if with_assistant:
                    assert payload["text"] == "Partial answer"
                else:
                    assert payload["text"] == ""
                await page.locator(".whitespace-pre-wrap").evaluate(
                    "node => node.textContent = 'Different prompt'",
                )
                altered = await page.evaluate(script, isolated_context=False)
                assert altered["verified"] is False
                assert altered["generating"] is False
            finally:
                await browser.close()

    asyncio.run(fixture())
