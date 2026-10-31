"""Modern ChatGPT reply segments remain one verified, recoverable turn."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from prompta.browser_script_loader import load_browser_script

CONVERSATION = "12345678-1234-4123-8123-123456789abc"
PARENT = "87654321-4321-4321-8321-123456789abc"
PART_A = "11111111-1111-4111-8111-111111111111"
PART_B = "22222222-2222-4222-8222-222222222222"


def _html(*, complete: bool = True, second_group: str = "fallback-turn-1") -> str:
    copy = '<button data-testid="copy-turn-action-button">Copy</button>' if complete else ""
    return f"""<html><body><main>
      <div data-chatgpt-search-unit-key="fallback-turn-0:0:user"><div class="whitespace-pre-wrap">Original prompt</div></div>
      <div data-chatgpt-search-unit-key="fallback-turn-0:2:assistant"
           data-chatgpt-search-message-ids="{PARENT} {PARENT} {PART_A}">
        <div class="markdown">Original answer</div>
      </div>
      <div data-chatgpt-search-unit-key="fallback-turn-1:0:user"><div class="whitespace-pre-wrap">Follow up</div></div>
      <article><div data-chatgpt-search-unit-key="fallback-turn-1:2:assistant"
          data-chatgpt-search-message-ids="{PART_A} {PART_A}">
          <div class="markdown"><p>First response</p></div>
      </div></article>
      <article><div data-chatgpt-search-unit-key="{second_group}:3:assistant"
          data-chatgpt-search-message-ids="{PART_B} {PART_B}">
          <div class="markdown"><p>Second response</p></div>
          </div>{copy}</article>
      </main></body></html>"""


def _historical_script() -> str:
    return (
        load_browser_script("historical_reply_probe.js")
        .replace("__CONVERSATION__", json.dumps(CONVERSATION))
        .replace("__ORIGINAL_PROMPT__", json.dumps("Original prompt"))
        .replace("__REPLY_TEXT__", json.dumps("Follow up"))
        .replace("__PARENT__", json.dumps(PARENT))
    )


def _delivery_script() -> str:
    return (
        load_browser_script("verify_manual_reply_delivery.js")
        .replace("__CONVERSATION__", json.dumps(CONVERSATION))
        .replace("__REPLY__", json.dumps("Follow up"))
        .replace("__PARENT__", json.dumps(PARENT))
    )


@pytest.mark.skipif(not Path("/usr/bin/chromium").exists(), reason="Chromium unavailable")
def test_multiunit_reply_historical_and_delivery_probes() -> None:
    async def check() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path="/usr/bin/chromium", headless=True)
            try:
                page = await browser.new_page()
                await page.route(
                    "https://chatgpt.com/c/**",
                    lambda route: route.fulfill(status=200, content_type="text/html", body=_html()),
                )
                await page.goto("https://chatgpt.com/c/" + CONVERSATION)
                historical = await page.evaluate(_historical_script())
                assert historical["verified"] is True
                assert historical["ambiguous"] is False
                assert historical["complete"] is True
                assert historical["verified_parent_id"] == PARENT
                assert historical["branch_message_id"] == PART_B
                assert historical["text"] == "First response\n\nSecond response"
                tip_script = (
                    load_browser_script("recover_manual_reply_tip.js")
                    .replace("__CONVERSATION__", json.dumps(CONVERSATION))
                    .replace("__PARENT__", json.dumps(PARENT))
                    .replace("__USER_TEXT__", json.dumps("Follow up"))
                    .replace("__ASSISTANT_TEXT__", json.dumps("First response"))
                    .replace("__TURN_COUNT__", "2")
                )
                assert await page.evaluate(tip_script) == PART_B
                delivery = await page.evaluate(_delivery_script())
                assert delivery == {
                    "verified": True, "complete": True, "message_id": PART_B,
                    "text": "First response\n\nSecond response",
                }

                # Immediate delivery verification also supports later explicit replies.
                third_id = "33333333-3333-4333-8333-333333333333"
                third = f"""<div data-chatgpt-search-unit-key="fallback-turn-2:0:user">Next reply</div>
                    <article><div data-chatgpt-search-unit-key="fallback-turn-2:2:assistant"
                        data-chatgpt-search-message-ids="{third_id}">
                        <div class="markdown"><p>Third response</p></div></div>
                        <button data-testid="copy-turn-action-button">Copy</button></article>"""
                await page.locator("main").evaluate(
                    "(main, html) => main.insertAdjacentHTML('beforeend', html)", third
                )
                third_script = (
                    load_browser_script("verify_manual_reply_delivery.js")
                    .replace("__CONVERSATION__", json.dumps(CONVERSATION))
                    .replace("__REPLY__", json.dumps("Next reply"))
                    .replace("__PARENT__", json.dumps(PART_B))
                )
                third_tip = (
                    load_browser_script("recover_manual_reply_tip.js")
                    .replace("__CONVERSATION__", json.dumps(CONVERSATION))
                    .replace("__PARENT__", json.dumps(PART_B))
                    .replace("__USER_TEXT__", json.dumps("Next reply"))
                    .replace("__ASSISTANT_TEXT__", json.dumps("Third response"))
                    .replace("__TURN_COUNT__", "3")
                )
                assert await page.evaluate(third_tip) == third_id
                third_result = await page.evaluate(third_script)
                assert third_result == {
                    "verified": True, "complete": True,
                    "message_id": third_id, "text": "Third response",
                }
                await page.locator('[data-chatgpt-search-unit-key="fallback-turn-2:0:user"]').evaluate(
                    "node => node.remove()"
                )
                await page.locator('[data-chatgpt-search-unit-key="fallback-turn-2:2:assistant"]').evaluate(
                    "node => node.closest('article').remove()"
                )

                await page.locator('button[data-testid="copy-turn-action-button"]').evaluate("node => node.remove()")
                partial = await page.evaluate(_historical_script())
                assert partial["verified"] is True
                assert partial["complete"] is False
                assert partial["branch_message_id"] == ""
                assert partial["text"] == "First response\n\nSecond response"

                await page.locator('[data-chatgpt-search-unit-key="fallback-turn-1:3:assistant"]').evaluate(
                    "node => node.setAttribute('data-chatgpt-search-unit-key', 'fallback-turn-2:3:assistant')"
                )
                different = await page.evaluate(_historical_script())
                assert different["ambiguous"] is True
                assert different["text"] == ""
            finally:
                await browser.close()

    asyncio.run(check())


@pytest.mark.skipif(not Path("/usr/bin/chromium").exists(), reason="Chromium unavailable")
def test_passive_observer_aggregates_new_reply_segments() -> None:
    async def check() -> None:
        async with async_playwright() as playwright:
            browser = await playwright.chromium.launch(executable_path="/usr/bin/chromium", headless=True)
            try:
                page = await browser.new_page()
                await page.route(
                    "https://chatgpt.com/c/**",
                    lambda route: route.fulfill(
                        status=200, content_type="text/html",
                        body=f"""<html><body><main>
                          <div data-chatgpt-search-unit-key="fallback-turn-0:0:user">Original prompt</div>
                          <div data-chatgpt-search-unit-key="fallback-turn-0:2:assistant"
                               data-chatgpt-search-message-ids="{PARENT}">
                            <div class="markdown">Original answer</div>
                          </div></main></body></html>""",
                    ),
                )
                await page.goto("https://chatgpt.com/c/" + CONVERSATION)
                await page.evaluate(load_browser_script("passive_response_observer.js"))
                later = f"""<div data-chatgpt-search-unit-key="fallback-turn-1:0:user">Follow up</div>
                    <article><div data-chatgpt-search-unit-key="fallback-turn-1:2:assistant"
                        data-chatgpt-search-message-ids="{PART_A} {PART_A}">
                        <div class="markdown"><p>First response</p></div></div></article>
                    <article id="last-reply"><div data-chatgpt-search-unit-key="fallback-turn-1:3:assistant"
                        data-chatgpt-search-message-ids="{PART_B} {PART_B}">
                        <div class="markdown"><p>Second response</p></div></div></article>"""
                await page.locator("main").evaluate(
                    "(main, html) => main.insertAdjacentHTML('beforeend', html)", later
                )
                await page.wait_for_timeout(1100)
                interim = await page.evaluate("window.__promptaPassiveResponseObserver.read()")
                assert interim["ambiguous"] is False
                assert interim["message_id"] == "fallback-turn-1"
                assert interim["text"] == "First response\n\nSecond response"
                assert interim["complete"] is False
                await page.locator("#last-reply").evaluate(
                    """(node) => node.insertAdjacentHTML('beforeend',
                    '<button data-testid="copy-turn-action-button">Copy</button>')"""
                )
                await page.wait_for_timeout(1100)
                finished = await page.evaluate("window.__promptaPassiveResponseObserver.read()")
                assert finished["ambiguous"] is False
                assert finished["complete"] is True
                assert finished["branch_message_id"] == PART_B
                assert finished["text"] == "First response\n\nSecond response"
            finally:
                await browser.close()

    asyncio.run(check())
