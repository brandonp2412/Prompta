"""The chat rail reports recoverable backlog without navigating ChatGPT."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from test_web_results import completed_run, server


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_sidebar_explains_recovery_backlog_and_read_cooldown(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "local-recovery-chat", "Local test chat", 1000)
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.route("**/api/events", lambda route: route.abort())
        page.route(
            "**/api/health",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body=json.dumps({"recovery": {
                    "attention_chats": 8,
                    "recoverable": 7,
                    "unresolved_reply_captures": 3,
                    "account_read_backoff_seconds": 1200,
                    "security_pause_seconds": 0,
                    "global_pace_seconds": 0,
                }}),
            ),
        )
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        summary = page.locator(".chat-recovery-summary")
        expect(summary).to_contain_text("7 original captures eligible")
        expect(summary).to_contain_text("3 follow-ups unresolved")
        expect(summary).to_contain_text("waiting ~20 min")
        expect(page.get_by_role("button", name="Needs attention 8 chats")).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        browser.close()
