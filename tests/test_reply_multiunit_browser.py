"""Modern ChatGPT reply segments remain one verified, recoverable turn."""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import pytest
from patchright.async_api import async_playwright as async_patchright

from prompta.browser_script_loader import load_browser_script
from prompta.reply_contracts import ManualReplyStore, ReplyIntent
from prompta.response_capture import CaptureResult, normalize_dom_snapshot
from prompta.response_store import ResponseStore

CONVERSATION = "12345678-1234-4123-8123-123456789abc"
PARENT = "87654321-4321-4321-8321-123456789abc"
PART_A = "11111111-1111-4111-8111-111111111111"
PART_B = "22222222-2222-4222-8222-222222222222"
TEST_CHROMIUM = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))


@pytest.mark.skipif(not TEST_CHROMIUM.exists(), reason="Chromium unavailable")
@pytest.mark.parametrize("followup", [False, True])
def test_recovery_accepts_new_final_id_only_with_saved_message_in_verified_turn(
    tmp_path: Path, followup: bool,
) -> None:
    store = ResponseStore(tmp_path / "results.sqlite3")
    replies = ManualReplyStore(store.path)
    store.ensure_queued("run", "Original prompt", now=10)
    assert store.accept("run", "123:owner", deadline=100, now=11)
    first = CaptureResult("sse", "partial", "First response", CONVERSATION, PART_A, None)
    if followup:
        assert store.write("run", "123:owner", CaptureResult(
            "sse", "complete", "Original answer", CONVERSATION, PARENT, None,
        ), now=12)
        intent = ReplyIntent("reply", CONVERSATION, PARENT, "Follow up")
        replies.prepare("run", intent, now=13)
        assert replies.claim("reply", "123:reply", deadline=100, now=14)
        assert replies.accepted(
            "reply", "123:reply", conversation_id=CONVERSATION, parent_id=PARENT,
            message_id=PART_A, now=14,
        )
        assert replies.observe("reply", "123:reply", CaptureResult(
            "sse", "partial", "First response", CONVERSATION, PART_A, PARENT,
        ), now=15)
        assert replies.finish("reply", "123:reply", uncertain=True, now=16)
    else:
        assert store.write("run", "123:owner", first, now=12)
        assert store.finish("run", "123:owner", "interrupted", now=13)

    async def check() -> None:
        async with async_patchright() as patchright:
            browser = await patchright.chromium.launch(executable_path=str(TEST_CHROMIUM), headless=True)
            try:
                page = await browser.new_page()
                html = _html() if followup else _html().split(
                    '<div data-chatgpt-search-unit-key="fallback-turn-1:0:user">'
                )[0].replace(
                    f'data-chatgpt-search-message-ids="{PARENT} {PARENT} {PART_A}"',
                    f'data-chatgpt-search-message-ids="{PART_A}"',
                ).replace('Original answer', 'First response') + f'''
                    <article><div data-chatgpt-search-unit-key="fallback-turn-0:3:assistant"
                        data-chatgpt-search-message-ids="{PART_B}">
                      <div class="markdown" data-talvt-turn-state="complete"><p>Second response</p></div></div>
                      <button data-testid="copy-turn-action-button">Copy</button>
                    </article></main></body></html>'''
                await page.route("https://chatgpt.com/c/**", lambda route: route.fulfill(
                    status=200, content_type="text/html", body=html,
                ))
                await page.goto("https://chatgpt.com/c/" + CONVERSATION)
                script = _historical_script() if followup else load_browser_script(
                    "historical_response_probe.js",
                ).replace("__CONVERSATION__", json.dumps(CONVERSATION)).replace(
                    "__ORIGINAL_PROMPT__", json.dumps("Original prompt"),
                )
                payload = await page.evaluate(script)
                assert payload["turn_message_ids"] == [PART_A, PART_B]
                assert payload["branch_message_id"] == PART_B
                capture = normalize_dom_snapshot(payload)
                assert capture.status == "complete"
                payload["turn_message_ids"] = [PART_B]
                unrelated = normalize_dom_snapshot(payload)
                if followup:
                    assert not replies.recover_historical_reply("reply", unrelated, now=20)
                    assert replies.recover_historical_reply("reply", capture, now=21)
                    row = replies.get("reply")
                else:
                    assert not store.recover_historical_response("run", unrelated, now=20)
                    assert store.recover_historical_response("run", capture, now=21)
                    row = store.get("run")
                assert row is not None and row["status"] == "completed"
                assert row["message_id"] == PART_B
                assert row["assistant_text"] == "First response\n\nSecond response"
            finally:
                await browser.close()

    asyncio.run(check())


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


@pytest.mark.skipif(not TEST_CHROMIUM.exists(), reason="Chromium unavailable")
def test_multiunit_reply_historical_and_delivery_probes() -> None:
    async def check() -> None:
        async with async_patchright() as patchright:
            browser = await patchright.chromium.launch(executable_path=str(TEST_CHROMIUM), headless=True)
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
                    "has_assistant": True, "generating": False, "error_visible": False,
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
                    "has_assistant": True, "generating": False, "error_visible": False,
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


@pytest.mark.skipif(not TEST_CHROMIUM.exists(), reason="Chromium unavailable")
def test_passive_observer_aggregates_new_reply_segments() -> None:
    async def check() -> None:
        async with async_patchright() as patchright:
            browser = await patchright.chromium.launch(executable_path=str(TEST_CHROMIUM), headless=True)
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


@pytest.mark.skipif(not TEST_CHROMIUM.exists(), reason="Chromium unavailable")
def test_rich_answer_source_id_overrides_aggregate_reference_ids() -> None:
    async def check() -> None:
        async with async_patchright() as runtime:
            browser = await runtime.chromium.launch(executable_path=str(TEST_CHROMIUM), headless=True)
            try:
                page = await browser.new_page()
                html = _html().replace(
                    f'data-chatgpt-search-message-ids="{PART_B} {PART_B}"',
                    f'data-chatgpt-search-message-ids="{PART_B} {PART_B} {PART_A}"',
                ).replace(
                    '<p>Second response</p>',
                    f'<div data-dil-source-message-id="{PART_B}"><p>Second response</p></div>',
                )
                await page.route("https://chatgpt.com/c/**", lambda route: route.fulfill(
                    content_type="text/html", body=html,
                ))
                await page.goto("https://chatgpt.com/c/" + CONVERSATION)
                result = normalize_dom_snapshot(await page.evaluate(_historical_script()))
                assert result.status == "complete"
                assert result.message_id == PART_B
                assert result.text == "First response\n\nSecond response"
                # Multiple visible source messages remain ambiguous.
                await page.locator('[data-dil-source-message-id]').evaluate(
                    "(node, id) => node.insertAdjacentHTML('afterend', "
                    "'<div data-dil-source-message-id=\"' + id + '\">Other</div>')", PART_A,
                )
                ambiguous = normalize_dom_snapshot(await page.evaluate(_historical_script()))
                assert ambiguous.status != "complete"
                assert ambiguous.message_id is None
            finally:
                await browser.close()
    asyncio.run(check())
