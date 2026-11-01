"""A real browser must verify the owned turn before granting a recovered tool call."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from patchright.async_api import async_playwright as async_patchright

from prompta.browser_script_loader import load_browser_script
from prompta.history_recovery import _guarded_approval_script

CONVERSATION = "12345678-1234-4123-8123-123456789abc"
HTML = """<html><body><main>
<article><div data-message-author-role="user"><div class="whitespace-pre-wrap">Original prompt</div></div></article>
<article><div data-message-author-role="assistant" data-message-id="assistant-one">
<div class="markdown">Working on it</div>
</div><button data-testid="copy-turn-action-button">Copy</button></article>
</main><div role="dialog" id="permission">
  <button id="always-allow">Always allow</button>
  <button>Allow once</button><button>Deny</button>
</div></body></html>"""


@pytest.mark.asyncio
async def test_exact_recovered_capture_can_approve_but_never_later_user_turn() -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.exists():
        pytest.skip("Chromium fixture browser not available")
    probe = load_browser_script("historical_response_probe.js").replace(
        "__CONVERSATION__", json.dumps(CONVERSATION)
    ).replace("__ORIGINAL_PROMPT__", json.dumps("Original prompt"))
    approval = _guarded_approval_script(probe, single_user_only=True)

    async with async_patchright() as patchright:
        browser = await patchright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"],
        )
        try:
            page = await browser.new_page()
            await page.route(
                "https://chatgpt.com/c/**",
                lambda route: route.fulfill(
                    status=200, content_type="text/html", body=HTML,
                ),
            )
            await page.goto("https://chatgpt.com/c/" + CONVERSATION)
            await page.evaluate("""() => {
                window.__grants = 0;
                document.getElementById('always-allow').addEventListener('click', () => {
                    window.__grants += 1;
                    document.getElementById('permission').hidden = true;
                });
            }""")
            preliminary = await page.evaluate(probe)
            assert preliminary["verified"] is True and preliminary["complete"] is True
            assert await page.evaluate(approval) is True
            assert await page.evaluate("window.__grants") == 1

            # A later user message changes ownership of the visible permission.
            # The historical first-turn probe remains verified, but resuming
            # that old turn must not approve the current user's tool.
            await page.evaluate("""() => {
                document.getElementById('permission').hidden = false;
                const turn = document.createElement('article');
                turn.innerHTML = '<div data-message-author-role="user">Later user message</div>';
                document.querySelector('main').appendChild(turn);
            }""")
            assert await page.evaluate(approval) is False
            assert await page.evaluate("window.__grants") == 1

            await page.locator('[data-message-author-role="user"]').first.evaluate(
                "node => node.textContent = 'Unrelated prompt'"
            )
            assert await page.evaluate(approval) is False
            assert await page.evaluate("window.__grants") == 1
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_recovered_reply_cannot_approve_a_newer_reply_branch() -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.exists():
        pytest.skip("Chromium fixture browser not available")
    parent = "11111111-1111-4111-8111-111111111111"
    reply_html = f"""<main>
      <article><div data-message-author-role="user"><div class="whitespace-pre-wrap">Original prompt</div></div></article>
      <article><div data-message-author-role="assistant" data-message-id="{parent}">
        <div class="markdown">Parent answer</div></div></article>
      <article><div data-message-author-role="user"><div class="whitespace-pre-wrap">My reply</div></div></article>
      <article><div data-message-author-role="assistant" data-message-id="22222222-2222-4222-8222-222222222222">
        <div class="markdown">Reply in progress</div></div></article>
    </main><div role="dialog" id="permission">
      <button id="always-allow">Always allow</button><button>Allow once</button><button>Deny</button>
    </div>"""
    probe = (load_browser_script("historical_reply_probe.js")
             .replace("__CONVERSATION__", json.dumps(CONVERSATION))
             .replace("__ORIGINAL_PROMPT__", json.dumps("Original prompt"))
             .replace("__REPLY_TEXT__", json.dumps("My reply"))
             .replace("__PARENT__", json.dumps(parent)))
    approval = _guarded_approval_script(probe, single_user_only=False)
    async with async_patchright() as patchright:
        browser = await patchright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"],
        )
        try:
            page = await browser.new_page()
            await page.route(
                "https://chatgpt.com/c/**",
                lambda route: route.fulfill(
                    status=200, content_type="text/html", body=reply_html,
                ),
            )
            await page.goto("https://chatgpt.com/c/" + CONVERSATION)
            await page.evaluate("""() => {
                window.__grants = 0;
                document.getElementById('always-allow').addEventListener('click', () => {
                    window.__grants += 1;
                    document.getElementById('permission').hidden = true;
                });
            }""")
            proof = await page.evaluate(probe)
            assert proof["verified"] is True and proof["ambiguous"] is False
            assert await page.evaluate(approval) is True
            assert await page.evaluate("window.__grants") == 1

            await page.evaluate("""() => {
                document.getElementById('permission').hidden = false;
                const newer = document.createElement('article');
                newer.innerHTML = '<div data-message-author-role="user">Later reply</div>';
                document.querySelector('main').appendChild(newer);
            }""")
            assert await page.evaluate(approval) is False
            assert await page.evaluate("window.__grants") == 1
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_still_visible_permission_reports_pending_during_retry_backoff() -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.exists():
        pytest.skip("Chromium fixture browser not available")
    probe = load_browser_script("historical_response_probe.js").replace(
        "__CONVERSATION__", json.dumps(CONVERSATION)
    ).replace("__ORIGINAL_PROMPT__", json.dumps("Original prompt"))
    approval = _guarded_approval_script(probe, single_user_only=True)
    async with async_patchright() as patchright:
        browser = await patchright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"],
        )
        try:
            page = await browser.new_page()
            await page.route(
                "https://chatgpt.com/c/**",
                lambda route: route.fulfill(status=200, content_type="text/html", body=HTML),
            )
            await page.goto("https://chatgpt.com/c/" + CONVERSATION)
            # An unhydrated button ignores the DOM click. A retry must remain
            # pending; a copy-ready earlier chunk does not prove finality.
            assert await page.evaluate(approval) == "stuck"
            assert await page.evaluate(approval) == "pending"
        finally:
            await browser.close()
