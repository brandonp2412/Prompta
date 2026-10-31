"""Chromium proof that read-only recovery works for later exact-branch replies."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from patchright.sync_api import sync_playwright

from prompta.browser_script_loader import load_browser_script

CONVERSATION = "12345678-1234-4123-8123-123456789abc"
ORIGINAL_ID = "11111111-1111-4111-8111-111111111111"
FIRST_ID = "22222222-2222-4222-8222-222222222222"
SECOND_ID = "33333333-3333-4333-8333-333333333333"


def test_second_followup_probe_requires_full_original_lineage_and_final_copy() -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    script = (
        load_browser_script("historical_reply_probe.js")
        .replace("__CONVERSATION__", json.dumps(CONVERSATION))
        .replace("__ORIGINAL_PROMPT__", json.dumps("Original prompt"))
        .replace("__REPLY_TEXT__", json.dumps("Second follow-up"))
        .replace("__PARENT__", json.dumps(FIRST_ID))
    )
    html = f"""<html><body><main>
    <article><div data-message-author-role="user">Original prompt</div></article>
    <article><div data-message-author-role="assistant" data-message-id="{ORIGINAL_ID}">
      <div class="markdown">Original answer</div></div>
      <button data-testid="copy-turn-action-button">Copy</button></article>
    <article><div data-message-author-role="user">First follow-up</div></article>
    <article><div data-message-author-role="assistant" data-message-id="{FIRST_ID}">
      <div class="markdown">First answer</div></div>
      <button data-testid="copy-turn-action-button">Copy</button></article>
    <article><div data-message-author-role="user">Second follow-up</div></article>
    <article><div data-message-author-role="assistant" data-message-id="{SECOND_ID}">
      <div class="markdown"><p>Second final answer</p></div></div>
      <button class="target-copy" data-testid="copy-turn-action-button">Copy</button></article>
    </main></body></html>"""
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"],
        )
        try:
            page = browser.new_page()
            routed: list[str] = []

            def serve(route: object) -> None:
                from patchright.sync_api import Route

                assert isinstance(route, Route)
                routed.append(route.request.url)
                route.fulfill(status=200, content_type="text/html", body=html)

            page.route("https://chatgpt.com/c/**", serve)
            page.goto("https://chatgpt.com/c/" + CONVERSATION)
            result = page.evaluate(script)
            assert result["verified"] is True and result["complete"] is True
            assert result["verified_parent_id"] == FIRST_ID
            assert result["branch_message_id"] == SECOND_ID
            assert result["text"] == "Second final answer"

            # An earlier answer's Copy control is not completion evidence for
            # the target reply, even when the final answer already has an ID.
            page.locator(".target-copy").evaluate("(node) => node.remove()")
            pending = page.evaluate(script)
            assert pending["verified"] is True and pending["complete"] is False

            page.locator('[data-message-author-role="user"]').first.evaluate(
                "(node) => node.textContent = 'Different original'"
            )
            wrong_origin = page.evaluate(script)
            assert wrong_origin["verified"] is False and wrong_origin["ambiguous"] is True
            assert routed == ["https://chatgpt.com/c/" + CONVERSATION]
        finally:
            browser.close()
