"""Real browser proof: Stop targets only the owned, exact ChatGPT generation."""

import os
from pathlib import Path

import pytest
from patchright.async_api import async_playwright

from prompta.stop_jobs import click_chatgpt_stop


async def test_stop_button_targets_exact_owned_chat(
    unused_tcp_port: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    monkeypatch.setenv("PROMPTA_CHROME_DEBUGGER_ADDRESS", f"127.0.0.1:{unused_tcp_port}")
    conversation = "12345678-1234-4123-8123-123456789abc"
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox", f"--remote-debugging-port={unused_tcp_port}"],
        )
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.route(
                "https://chatgpt.com/**",
                lambda route: route.fulfill(
                    body='<div data-message-author-role="assistant" data-message-id="answer"></div>'
                    '<button data-testid="stop-button" onclick="this.textContent=\'Stopped\'">Stop generating</button>',
                    content_type="text/html",
                ),
            )
            await page.goto(f"https://chatgpt.com/c/{conversation}")
            assert not await click_chatgpt_stop(conversation, "answer")
            await page.evaluate("window.name = 'prompta-delivery:123:owner:tab'")
            assert not await click_chatgpt_stop("00000000-1234-4123-8123-123456789abc", "answer")
            assert not await click_chatgpt_stop(conversation, "wrong-answer")
            assert await click_chatgpt_stop(conversation, "answer")
            assert await page.get_by_test_id("stop-button").inner_text() == "Stopped"
            assert browser.is_connected()
            assert not page.is_closed()
        finally:
            await browser.close()


async def test_stop_button_matches_modern_chatgpt_message_ids(
    unused_tcp_port: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    monkeypatch.setenv("PROMPTA_CHROME_DEBUGGER_ADDRESS", f"127.0.0.1:{unused_tcp_port}")
    conversation = "12345678-1234-4123-8123-123456789abc"
    expected = "aaaaaaaa-1234-4123-8123-123456789abc"
    unrelated = "bbbbbbbb-1234-4123-8123-123456789abc"
    async with async_playwright() as runtime:
        browser = await runtime.chromium.launch(
            executable_path=str(chromium),
            headless=True,
            args=["--no-sandbox", f"--remote-debugging-port={unused_tcp_port}"],
        )
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.route(
                "https://chatgpt.com/**",
                lambda route: route.fulfill(
                    body=f'<main><div data-chatgpt-search-unit-key="fallback-turn-0:2:assistant" '
                    f'data-chatgpt-search-message-ids="{expected} {expected}">Answer</div>'
                    '<button aria-label="Stop streaming" onclick="this.textContent=\'Stopped\'">'
                    "Stop</button></main>",
                    content_type="text/html",
                ),
            )
            await page.goto(f"https://chatgpt.com/c/{conversation}")
            await page.evaluate("window.name = 'prompta-delivery:123:owner:tab'")
            assert not await click_chatgpt_stop(conversation, unrelated)
            assert await page.get_by_role("button", name="Stop streaming").inner_text() == "Stop"
            assert await click_chatgpt_stop(conversation, expected)
            assert await page.get_by_role("button", name="Stop streaming").inner_text() == "Stopped"
            await page.evaluate(
                """(unrelated) => {
                const main = document.querySelector("main");
                const newer = document.createElement("div");
                newer.setAttribute("data-chatgpt-search-unit-key", "fallback-turn-1:2:assistant");
                newer.setAttribute("data-chatgpt-search-message-ids", JSON.stringify([unrelated]));
                main.append(newer);
            }""",
                unrelated,
            )
            assert not await click_chatgpt_stop(conversation, expected)
        finally:
            await browser.close()
