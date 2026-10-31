"""Browser proof that damaged or terminal fresh receipts never trigger duplicate POSTs."""
from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import Route, expect, sync_playwright
from test_web_results import server


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_unknown_delivery_receipt_is_not_presented_as_success(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            posts: list[str] = []

            def lose_acknowledgment(route: Route) -> None:
                posts.append(route.request.post_data or "")
                assert route.fetch().status == 202
                route.fulfill(status=503, body="Simulated lost receipt")

            page.route("**/api/chats", lose_acknowledgment)
            page.route("**/api/chats/requests/*", lambda route: route.fulfill(status=503))
            page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
            draft = page.get_by_role("textbox", name="Message for new chat")
            draft.fill("A fresh response may already exist")
            page.get_by_role("button", name="Send fresh chat").click()
            expect(page.get_by_text("Queue receipt is uncertain.", exact=False)).to_be_visible()
            assert len(posts) == 1
            records = app.queue.records()
            assert len(records) == 1
            claimed = app.queue.claim_next("browser-test", lease_seconds=300)
            assert claimed is not None
            assert app.queue.fail_claim(
                str(claimed["send_id"]), "browser-test",
                status="outcome_unknown", error="Response is uncertain",
            )

            page.unroute("**/api/chats/requests/*")
            page.reload()
            expect(draft).to_have_value("A fresh response may already exist")
            page.get_by_role("button", name="Send fresh chat").click()
            expect(page.get_by_text("may have reached ChatGPT", exact=False)).to_be_visible()
            assert len(posts) == 1, "An uncertain send cannot be automatically repeated"
            terminal = app.queue.get(str(claimed["send_id"]))
            assert terminal is not None
            assert terminal["status"] == "outcome_unknown"
            browser.close()


def test_corrupt_receipt_ledger_blocks_post_and_retains_draft(tmp_path: Path) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port):
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page(viewport={"width": 390, "height": 844})
            posts: list[str] = []
            page.on("request", lambda request: posts.append(request.url)
                    if request.url.endswith("/api/chats") and request.method == "POST" else None)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
            page.evaluate("localStorage.setItem('prompta.pending-fresh-requests.v1', '{')")
            draft = page.get_by_role("textbox", name="Message for new chat")
            draft.fill("Preserve this unsent text")
            page.get_by_role("button", name="Send fresh chat").click()
            expect(page.get_by_text("Unresolved chat receipts are unreadable", exact=False)).to_be_visible()
            expect(draft).to_have_value("Preserve this unsent text")
            assert posts == []
            assert app.queue.records() == []
            assert page.evaluate("localStorage.getItem('prompta.pending-fresh-requests.v1')") == "{"
            browser.close()
