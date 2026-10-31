"""Browser regression: a lost early-follow-up POST receipt never creates another send."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import Route, expect, sync_playwright
from test_stage5_composer import serve_test_ui

from prompta.reply_contracts import ManualReplyStore
from prompta.response_store import ResponseStore


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_lost_followup_receipt_recovers_from_local_sqlite_without_second_post(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    results = ResponseStore(tmp_path / "chat-results.sqlite3")
    results.ensure_queued("lost-receipt", "Original", now=time.time())
    assert results.accept("lost-receipt", "owner", deadline=time.time() + 4000)
    with serve_test_ui(tmp_path) as port, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.route("**/api/events", lambda route: route.abort())
        page.goto(f"http://127.0.0.1:{port}/?view=chats&run=lost-receipt")
        composer = page.get_by_role("textbox", name="Message for current chat")
        expect(composer).to_be_enabled()

        posts = 0

        def lose_post(route: Route) -> None:
            nonlocal posts
            posts += 1
            response = route.fetch()
            assert response.status == 202
            route.abort("failed")

        page.route("**/api/results/lost-receipt/reply-queue", lose_post)
        page.route(
            "**/api/results/lost-receipt/turns",
            lambda route: route.fulfill(status=503, body="Local outage"),
        )
        composer.fill("An explicit queued follow-up")
        expect(page.get_by_role("button", name="Send reply")).to_be_enabled()
        composer.press("Enter")
        expect(page.get_by_text("Queue receipt was lost", exact=False)).to_be_visible()
        expect(composer).to_have_value("An explicit queued follow-up")
        assert posts == 1
        assert len(ManualReplyStore(results.path).turns("lost-receipt") or []) == 2

        page.unroute("**/api/results/lost-receipt/turns")
        page.reload()
        composer = page.get_by_role("textbox", name="Message for current chat")
        expect(composer).to_have_value("An explicit queued follow-up")
        expect(page.get_by_role("button", name="Send reply")).to_be_enabled()
        composer.press("Enter")
        expect(composer).to_have_value("")
        expect(page.get_by_text("An explicit queued follow-up")).to_be_visible()
        assert posts == 1
        saved = ManualReplyStore(results.path).turns("lost-receipt") or []
        assert len(saved) == 2 and saved[-1]["status"] == "queued"
        browser.close()
