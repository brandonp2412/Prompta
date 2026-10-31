"""Browser E2E: a lost exact reply HTTP receipt is reconciled locally without replay."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import Route, expect, sync_playwright
from test_reply_ui_browser import CONVERSATION, seed_terminal
from test_web_results import server

SEND_ID = "lost-reply-receipt"


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_lost_reply_post_receipt_reconciles_without_a_second_post(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, width: int, height: int,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static",
    )
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        seed_terminal(app, send_id=SEND_ID, missing_id=False)
        browser = playwright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            posts: list[str] = []

            def lose_response(route: Route) -> None:
                posts.append(route.request.post_data or "")
                response = route.fetch()
                assert response.status == 202
                # Server committed the immutable, explicitly queued reply.
                # Only the browser's response is lost, not the actual POST.
                route.abort("failed")

            page.route(f"**/api/results/{SEND_ID}/reply-send", lose_response)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run={SEND_ID}")
            expect(page.get_by_role("link", name="Open exact chat in ChatGPT")).to_have_attribute(
                "href", "https://chatgpt.com/c/" + CONVERSATION,
            )
            field = page.get_by_role("textbox", name="Message for current chat")
            field.fill("Recover this exact POST receipt")
            with page.expect_request(f"**/api/results/{SEND_ID}/reply-send"):
                page.get_by_role("button", name="Send reply").click()
            expect(field).to_have_value("")
            assert len(posts) == 1
            turns = app.replies.turns(SEND_ID)
            assert turns is not None and len(turns) == 2
            assert turns[1]["user_text"] == "Recover this exact POST receipt"
            assert turns[1]["queued_by_user"] is True
            assert turns[1]["status"] == "prepared"
            page.reload()
            expect(page.get_by_text("Recover this exact POST receipt")).to_be_visible()
            assert len(posts) == 1
        finally:
            browser.close()


def test_malformed_reply_receipt_does_not_clear_draft(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    import prompta.web as web_module

    monkeypatch.setattr(
        web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static",
    )
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        seed_terminal(app, send_id="malformed-receipt", missing_id=False)
        browser = playwright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.route(
                "**/api/results/malformed-receipt/reply-send",
                lambda route: route.fulfill(
                    status=202, content_type="application/json",
                    body='{"ok":true,"turn":{"status":"prepared"}}',
                ),
            )
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=malformed-receipt")
            field = page.get_by_role("textbox", name="Message for current chat")
            field.fill("Do not lose this draft")
            page.get_by_role("button", name="Send reply").click()
            expect(page.get_by_text("The reply receipt did not match its saved identity.", exact=False)).to_be_visible()
            assert field.input_value() == "Do not lose this draft"
            assert app.replies.turns("malformed-receipt") is not None
            assert len(app.replies.turns("malformed-receipt") or []) == 1
        finally:
            browser.close()
