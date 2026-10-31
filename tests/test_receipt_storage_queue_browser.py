"""Browser checks for durable send receipts and stale queue status."""
from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from patchright.sync_api import Route, expect, sync_playwright
from test_reply_ui_browser import seed_terminal
from web_results_support import server

CHROMIUM = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_browser_refuses_fresh_send_when_receipt_cannot_persist(
    tmp_path: Path, width: int, height: int,
) -> None:
    if not CHROMIUM.is_file():
        pytest.skip("Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(CHROMIUM), headless=True, args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.add_init_script("""
                (() => {
                    const original = Storage.prototype.setItem;
                    Storage.prototype.setItem = function(key, value) {
                        if (key === 'prompta.pending-fresh-requests.v1')
                            throw new DOMException('Storage denied', 'QuotaExceededError');
                        return original.call(this, key, value);
                    };
                })();
            """)
            posts: list[str] = []
            page.on("request", lambda req: posts.append(req.url)
                    if req.method == "POST" and req.url.endswith("/api/chats") else None)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
            draft = page.get_by_role("textbox", name="Message for new chat")
            draft.fill("Keep this draft if browser storage is full")
            page.get_by_role("button", name="Send fresh chat").click()
            expect(page.get_by_text("cannot be saved in browser storage", exact=False)).to_be_visible()
            expect(draft).to_have_value("Keep this draft if browser storage is full")
            assert posts == []
            assert app.queue.records() == []
        finally:
            browser.close()


def test_browser_refuses_exact_reply_when_receipt_cannot_persist(tmp_path: Path) -> None:
    if not CHROMIUM.is_file():
        pytest.skip("Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        seed_terminal(app, send_id="storage-reply-test", missing_id=False)
        browser = playwright.chromium.launch(
            executable_path=str(CHROMIUM), headless=True, args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": 390, "height": 844})
            page.add_init_script("""
                (() => {
                    const original = Storage.prototype.setItem;
                    Storage.prototype.setItem = function(key, value) {
                        if (key === 'prompta.pending-exact-replies.v1')
                            throw new DOMException('Storage denied', 'QuotaExceededError');
                        return original.call(this, key, value);
                    };
                })();
            """)
            posts: list[str] = []
            page.on("request", lambda req: posts.append(req.url)
                    if req.method == "POST" and req.url.endswith("/reply-send") else None)
            page.goto(f"http://127.0.0.1:{port}/?view=chats&run=storage-reply-test")
            draft = page.get_by_role("textbox", name="Message for current chat")
            draft.fill("Keep this exact reply draft")
            page.get_by_role("button", name="Send reply").click()
            expect(page.get_by_text("cannot be saved in browser storage", exact=False)).to_be_visible()
            expect(draft).to_have_value("Keep this exact reply draft")
            assert posts == []
        finally:
            browser.close()


@pytest.mark.parametrize("width,height", [(390, 844), (1440, 900)])
def test_queue_outage_retains_last_confirmed_positions(
    tmp_path: Path, width: int, height: int,
) -> None:
    if not CHROMIUM.is_file():
        pytest.skip("Chromium unavailable")
    queue = {
        "max_workers": 3, "occupied_slots": 2,
        "estimated_run_seconds": 180, "estimate_samples": 4,
        "waiting": [{
            "name": "Scheduled queue probe", "position": 1, "reason": "global",
            "occupied": 2, "limit": 3, "eta_seconds": 180,
        }],
    }
    with server(tmp_path) as (_app, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(
            executable_path=str(CHROMIUM), headless=True, args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/events", lambda route: route.abort())
            failed = [False]

            def queue_response(route: Route) -> None:
                if failed[0]:
                    route.fulfill(status=503)
                else:
                    route.fulfill(status=200, content_type="application/json",
                                  body=json.dumps(queue))
            page.route("**/api/queue-status", queue_response)
            page.goto(f"http://127.0.0.1:{port}/?view=chats")
            expect(page.get_by_text("Scheduled queue probe")).to_be_visible()
            expect(page.get_by_text("ETA ~3 min", exact=False)).to_be_visible()
            failed[0] = True
            page.evaluate("window.dispatchEvent(new Event('online'))")
            expect(page.get_by_text("Showing the last confirmed positions", exact=False)).to_be_visible()
            expect(page.get_by_text("Scheduled queue probe")).to_be_visible()
            expect(page.get_by_text("ETA ~3 min", exact=False)).to_be_visible()
            failed[0] = False
            page.get_by_role("button", name="Retry queue status").click()
            expect(page.get_by_text("Showing the last confirmed positions", exact=False)).to_have_count(0)
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")
        finally:
            browser.close()
