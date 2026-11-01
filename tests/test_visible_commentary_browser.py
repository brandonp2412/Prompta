"""Browser proof for ordered visible commentary, tools, and final text."""

import asyncio
from pathlib import Path

import pytest
from patchright.async_api import async_playwright as async_patchright

from prompta.browser_script_loader import load_browser_script


@pytest.mark.skipif(not (Path.home() / ".cache/ms-playwright/chromium-1228/chrome-linux64/chrome").exists(), reason="Bundled Chromium unavailable")
def test_passive_observer_records_visible_commentary_before_tools() -> None:
    async def check() -> None:
        async with async_patchright() as patchright:
            browser = await patchright.chromium.launch(executable_path=str(Path.home() / ".cache/ms-playwright/chromium-1228/chrome-linux64/chrome"), headless=True)
            try:
                page = await browser.new_page()
                await page.goto("about:blank")
                await page.set_content("<html><body><main></main></body></html>")
                await page.evaluate(load_browser_script("passive_response_observer.js"))
                await page.locator("main").evaluate("""node => node.insertAdjacentHTML('beforeend', `
                  <article data-testid="conversation-turn-0">
                    <div data-message-author-role="assistant" data-message-id="answer-1">
                      <div class="markdown"><p>I'll check the source first.</p></div>
                      <button aria-label="Used Search">Used Search</button>
                      <section data-testid="reasoning-panel">
                        <div class="markdown"><p>Hidden analysis</p></div>
                      </section>
                      <div class="markdown"><p>Here is what I found.</p></div>
                    </div>
                  </article>`)
                """)
                observed = await page.evaluate("window.__promptaPassiveResponseObserver.read()")
                assert observed["text"] == "I'll check the source first.\n\nHere is what I found."
                assert observed["display_blocks"] == [
                    {"kind": "text", "id": "text-0", "text": "I'll check the source first."},
                    {"kind": "tool", "id": "dom-tool-0"},
                    {"kind": "text", "id": "text-1", "text": "Here is what I found."},
                ]
                assert len(observed["tool_calls"]) == 1
            finally:
                await browser.close()

    asyncio.run(check())
