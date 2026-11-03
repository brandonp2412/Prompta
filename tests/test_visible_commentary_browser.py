"""Browser proof for ordered visible commentary, tools, and final text."""

import asyncio
from pathlib import Path

import pytest
from patchright.async_api import async_playwright as async_patchright

from prompta.browser_script_loader import load_browser_script, passive_observer_init_script


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


@pytest.mark.skipif(not (Path.home() / ".cache/ms-playwright/chromium-1228/chrome-linux64/chrome").exists(), reason="Bundled Chromium unavailable")
def test_passive_observer_survives_full_chat_navigation() -> None:
    async def check() -> None:
        async with async_patchright() as patchright:
            browser = await patchright.chromium.launch(
                executable_path=str(Path.home() / ".cache/ms-playwright/chromium-1228/chrome-linux64/chrome"),
                headless=True,
            )
            try:
                page = await browser.new_page()
                await page.goto("about:blank")
                # This matches the order in the delivery worker: expose the
                # update binding, register the future-document observer, and
                # arm the current document before the user submits a prompt.
                updates: list[dict[str, object]] = []

                def on_update(payload: dict[str, object]) -> None:
                    updates.append(payload)

                await page.expose_function("__promptaPassiveUpdate", on_update)
                await page.add_init_script(passive_observer_init_script())
                assert await page.evaluate(load_browser_script("passive_response_observer.js"), isolated_context=False)
                # The fresh-chat route may load a completely new document.
                await page.goto("data:text/html,<html><body><main></main></body></html>")
                assert await page.evaluate(
                    "typeof window.__promptaPassiveResponseObserver === 'object'",
                    isolated_context=False,
                )
                await page.locator("main").evaluate("""node => node.insertAdjacentHTML('beforeend', `
                  <article data-chatgpt-search-unit-key="fallback-turn-0:2:assistant" data-chatgpt-search-message-ids="59188b32-a6b2-5b6d-9f58-59ed1ebaba53">
                    <div data-markdown-text-style="assistant-message"><p>Beginning text.</p></div>
                    <button aria-label="Used Search">Used Search</button>
                    <div data-markdown-text-style="assistant-message"><p>Intermediate text.</p></div>
                  </article>`)
                """)
                observed = await page.evaluate(
                    "window.__promptaPassiveResponseObserver.read()", isolated_context=False
                )
                assert observed["text"] == "Beginning text.\n\nIntermediate text."
                assert observed["display_blocks"] == [
                    {"kind": "text", "id": "text-0", "text": "Beginning text."},
                    {"kind": "tool", "id": "dom-tool-0"},
                    {"kind": "text", "id": "text-1", "text": "Intermediate text."},
                ]
            finally:
                await browser.close()

    asyncio.run(check())
