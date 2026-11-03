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
                # Modern ChatGPT commentary is a sibling of its final assistant
                # unit. It must become visible before that unit even exists.
                await page.locator("main").evaluate("""node => node.insertAdjacentHTML('beforeend', `
                  <div data-content-search-turn-key="fallback-turn-0">
                    <div data-content-search-unit-key="fallback-turn-0:0:user">
                      <div class="whitespace-pre-wrap">Test prompt, not assistant text.</div>
                    </div>
                    <div data-markdown-text-style="assistant-message" data-markdown-text-tone="primary"><p>Beginning text.</p></div>
                    <div class="group/activity-header">Used Search integration</div>
                    <div data-markdown-text-style="assistant-message" data-markdown-text-tone="primary"><p>Intermediate text.</p></div>
                    <div data-markdown-text-style="assistant-message" data-markdown-text-tone="tertiary"><p>Agent activity, not prose.</p></div>
                    <div id="assistant-slot"></div>
                  </div>`)
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
                await page.locator("#assistant-slot").evaluate("""node => node.innerHTML = `
                  <div data-chatgpt-search-unit-key="fallback-turn-0:2:assistant" data-chatgpt-search-message-ids="59188b32-a6b2-5b6d-9f58-59ed1ebaba53">
                    <div data-markdown-text-style="assistant-message"><p>Final text.</p></div>
                  </div>`
                """)
                observed = await page.evaluate(
                    "window.__promptaPassiveResponseObserver.read()", isolated_context=False
                )
                assert observed["text"] == "Beginning text.\n\nIntermediate text.\n\nFinal text."
                assert observed["display_blocks"][-1] == {
                    "kind": "text", "id": "text-2", "text": "Final text."
                }
                assert observed["branch_message_id"] == "59188b32-a6b2-5b6d-9f58-59ed1ebaba53"
            finally:
                await browser.close()

    asyncio.run(check())


@pytest.mark.skipif(not (Path.home() / ".cache/ms-playwright/chromium-1228/chrome-linux64/chrome").exists(), reason="Bundled Chromium unavailable")
def test_recovery_reads_commentary_siblings_on_exact_turn_only() -> None:
    async def check() -> None:
        async with async_patchright() as patchright:
            browser = await patchright.chromium.launch(
                executable_path=str(Path.home() / ".cache/ms-playwright/chromium-1228/chrome-linux64/chrome"),
                headless=True,
            )
            try:
                page = await browser.new_page()
                conversation = "12345678-1234-4123-8123-123456789abc"
                parent = "87654321-4321-4321-8321-123456789abc"
                answer = "59188b32-a6b2-5b6d-9f58-59ed1ebaba53"
                html = f"""<main>
                  <div data-turn-key="turn-0"><div data-content-search-turn-key="fallback-turn-0">
                    <div data-content-search-unit-key="fallback-turn-0:0:user"><div class="whitespace-pre-wrap">Original prompt</div></div>
                    <div data-markdown-text-style="assistant-message" data-markdown-text-tone="primary">Original opening.</div>
                    <div data-chatgpt-search-unit-key="fallback-turn-0:2:assistant" data-chatgpt-search-message-ids="{parent}">
                      <div data-markdown-text-style="assistant-message">Original final.</div>
                    </div>
                    <button data-testid="copy-turn-action-button">Copy</button>
                  </div></div>
                  <div data-turn-key="turn-1"><div data-content-search-turn-key="fallback-turn-1">
                    <div data-content-search-unit-key="fallback-turn-1:0:user"><div class="whitespace-pre-wrap">Follow up</div></div>
                    <div data-markdown-text-style="assistant-message" data-markdown-text-tone="primary">Reply opening.</div>
                    <div class="group/activity-header">Used Search integration</div>
                    <div data-markdown-text-style="assistant-message" data-markdown-text-tone="tertiary">Private activity summary.</div>
                    <div data-markdown-text-style="assistant-message" data-markdown-text-tone="primary">Reply middle.</div>
                    <div id="reply-final"></div>
                  </div></div>
                </main>"""
                await page.route("https://chatgpt.com/c/**", lambda route: route.fulfill(
                    status=200, content_type="text/html", body=html,
                ))
                await page.goto("https://chatgpt.com/c/" + conversation)
                history = (load_browser_script("historical_response_probe.js")
                    .replace("__CONVERSATION__", '"' + conversation + '"')
                    .replace("__ORIGINAL_PROMPT__", '"Original prompt"'))
                first = await page.evaluate(history, isolated_context=False)
                assert first["text"] == "Original opening.\n\nOriginal final."
                reply = (load_browser_script("historical_reply_probe.js")
                    .replace("__CONVERSATION__", '"' + conversation + '"')
                    .replace("__ORIGINAL_PROMPT__", '"Original prompt"')
                    .replace("__REPLY_TEXT__", '"Follow up"')
                    .replace("__PARENT__", '"' + parent + '"'))
                early = await page.evaluate(reply, isolated_context=False)
                assert early["text"] == "Reply opening.\n\nReply middle."
                assert early["complete"] is False
                assert early["message_id"] == "fallback-turn-1"
                assert early["display_blocks"] == [
                    {"kind": "text", "id": "text-0", "text": "Reply opening."},
                    {"kind": "tool", "id": "dom-tool-0"},
                    {"kind": "text", "id": "text-1", "text": "Reply middle."},
                ]
                await page.locator("#reply-final").evaluate("""(node, id) => {
                    node.innerHTML = `<div data-chatgpt-search-unit-key="fallback-turn-1:2:assistant"
                      data-chatgpt-search-message-ids="${id}">
                      <div data-markdown-text-style="assistant-message">Reply final.</div>
                    </div><button data-testid="copy-turn-action-button">Copy</button>`;
                }""", answer)
                done = await page.evaluate(reply, isolated_context=False)
                assert done["text"] == "Reply opening.\n\nReply middle.\n\nReply final."
                assert done["branch_message_id"] == answer
                assert done["message_id"] == early["message_id"]
                assert done["display_blocks"][-1] == {
                    "kind": "text", "id": "text-2", "text": "Reply final."
                }
                assert "Private activity summary" not in done["text"]
            finally:
                await browser.close()

    asyncio.run(check())
