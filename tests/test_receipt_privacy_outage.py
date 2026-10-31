"""Browser fault injection for receipt storage and local delivery status recovery."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from playwright.sync_api import Route, expect, sync_playwright
from test_stage5_composer import serve_test_ui
from test_web_results import server

from prompta.reply_contracts import ManualReplyStore
from prompta.response_store import ResponseStore


def _chromium() -> str:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    return executable


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_readable_unwritable_storage_never_changes_unconfirmed_fresh_request_id(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.add_init_script("""(() => {
          const original = Storage.prototype.setItem;
          Storage.prototype.setItem = function(key, value) {
            if (key === 'prompta.pending-fresh-requests.v1') {
              throw new DOMException('Storage quota exceeded', 'QuotaExceededError');
            }
            return original.call(this, key, value);
          };
        })()""")
        posts: list[str] = []

        def lose_first_receipt(route: Route) -> None:
            body = json.loads(route.request.post_data or "{}")
            posts.append(str(body["request_id"]))
            if len(posts) == 1:
                accepted = route.fetch()
                assert accepted.status == 202
                route.fulfill(status=503, body="Synthetic lost acknowledgement")
            else:
                route.continue_()

        page.route("**/api/events", lambda route: route.abort())
        page.route("**/api/chats", lose_first_receipt)
        page.route("**/api/chats/requests/*", lambda route: route.fulfill(status=503))
        page.goto(f"http://127.0.0.1:{port}/?view=chats&draft=new")
        page.get_by_role("textbox", name="Message for new chat").fill(
            "Synthetic blocked-storage receipt"
        )
        button = page.get_by_role("button", name="Send fresh chat")
        button.click()
        expect(page.get_by_text("Queue receipt is uncertain.", exact=False)).to_be_visible()
        assert len(app.queue.records()) == 1
        assert page.evaluate("localStorage.getItem('prompta.pending-fresh-requests.v1')") is None

        button.click()
        page.wait_for_url("**/?view=chats&run=manual-*")
        assert len(posts) == 2
        assert posts[0] == posts[1], "Same-page retries must reuse the original request ID"
        assert len(app.queue.records()) == 1, "One explicit chat may have only one queue record"
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_early_followup_uses_hashed_receipt_across_lost_ack_and_reload(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    results = ResponseStore(tmp_path / "chat-results.sqlite3")
    results.ensure_queued("early", "Original synthetic prompt")
    with serve_test_ui(tmp_path) as port, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        ids: list[str] = []

        def lose_receipt(route: Route) -> None:
            accepted = route.fetch()
            assert accepted.status == 202
            route.fulfill(status=503, body="Synthetic lost acknowledgement")

        page.route("**/api/events", lambda route: route.abort())
        page.route("**/api/results/early/reply-queue", lose_receipt)
        page.on(
            "request",
            lambda request: (
                ids.append(str(json.loads(request.post_data or "{}")["reply_id"]))
                if request.url.endswith("/reply-queue") and request.method == "POST"
                else None
            ),
        )
        page.goto(f"http://127.0.0.1:{port}/?view=chats&run=early")
        composer = page.get_by_role("textbox", name="Message for current chat")
        composer.fill("Synthetic private follow-up text")
        page.get_by_role("button", name="Send reply").click()
        # The new read-only local GET proves the queue was accepted even though
        # the POST response was lost; there must be no retry POST or pending draft.
        expect(composer).to_have_value("")
        expect(page.get_by_text("Synthetic private follow-up text")).to_be_visible()
        receipt = page.evaluate("localStorage.getItem('prompta.pending-exact-replies.v1')")
        assert isinstance(receipt, str)
        saved = json.loads(receipt)
        assert all(record["replyId"] != ids[0] for record in saved)
        assert "text" not in receipt
        assert "Synthetic private follow-up text" not in receipt

        page.unroute("**/api/results/early/reply-queue")
        page.reload()
        expect(page.get_by_text("Synthetic private follow-up text")).to_be_visible()
        expect(composer).to_have_value("")
        assert len(ids) == 1, "A verified SQLite receipt must avoid another POST after reload"
        turns = ManualReplyStore(results.path).turns("early")
        assert turns is not None
        assert len(turns) == 2, "Reconciliation must not enqueue another follow-up"
        remaining = page.evaluate("localStorage.getItem('prompta.pending-exact-replies.v1')")
        assert remaining is not None
        assert all(record["replyId"] != ids[0] for record in json.loads(remaining))
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_mismatched_followup_receipt_retains_id_and_does_not_duplicate(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    results = ResponseStore(tmp_path / "chat-results.sqlite3")
    results.ensure_queued("mismatch", "Original synthetic prompt")
    with serve_test_ui(tmp_path) as port, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        ids: list[str] = []

        def wrong_receipt(route: Route) -> None:
            accepted = route.fetch()
            assert accepted.status == 202
            route.fulfill(
                status=202, content_type="application/json", body='{"turn":{"reply_id":"wrong"}}'
            )

        page.route("**/api/events", lambda route: route.abort())
        page.route("**/api/results/mismatch/reply-queue", wrong_receipt)
        page.on(
            "request",
            lambda request: (
                ids.append(str(json.loads(request.post_data or "{}")["reply_id"]))
                if request.url.endswith("/reply-queue") and request.method == "POST"
                else None
            ),
        )
        page.goto(f"http://127.0.0.1:{port}/?view=chats&run=mismatch")
        composer = page.get_by_role("textbox", name="Message for current chat")
        composer.fill("Keep this immutable follow-up")
        # A forged/mismatched POST receipt is never enough to acknowledge. Block
        # the local GET once so the draft and original ID remain unresolved.
        page.route("**/api/results/mismatch/turns", lambda route: route.fulfill(status=503))
        page.get_by_role("button", name="Send reply").click()
        expect(page.get_by_text("Follow-up receipt did not match.", exact=False)).to_be_visible()
        expect(composer).to_have_value("Keep this immutable follow-up")
        receipt = page.evaluate("localStorage.getItem('prompta.pending-exact-replies.v1')")
        assert isinstance(receipt, str)
        assert any(item["replyId"] == ids[0] for item in json.loads(receipt))
        page.unroute("**/api/results/mismatch/turns")
        # Now SQLite can prove the intent was accepted; no new POST may occur.
        page.get_by_role("button", name="Send reply").click()
        expect(composer).to_have_value("")
        assert len(ids) == 1
        turns = ManualReplyStore(results.path).turns("mismatch")
        assert turns is not None and len(turns) == 2
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_jobs_refresh_outage_has_visible_recovery_and_no_false_online_status(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    with server(tmp_path) as (_, port), sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=_chromium(), headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.clock.install()
        page.route("**/api/events", lambda route: route.abort())
        page.goto(f"http://127.0.0.1:{port}/?view=jobs")
        refresh = page.get_by_role("button", name="Refresh jobs")
        expect(refresh).to_be_visible()
        expect(page.locator(".delivery-diagnostics")).to_be_visible()

        page.route("**/api/jobs", lambda route: route.fulfill(status=503))
        refresh.click()
        expect(page.get_by_role("button", name="Retry jobs")).to_be_visible()
        expect(page.get_by_text("The list may be out of date.", exact=False)).to_be_visible()
        page.unroute("**/api/jobs")
        page.get_by_role("button", name="Retry jobs").click()
        expect(page.get_by_role("button", name="Retry jobs")).to_have_count(0)

        page.route("**/api/health", lambda route: route.fulfill(status=503))
        page.clock.fast_forward(31000)
        expect(page.locator(".delivery-diagnostics")).to_contain_text("Delivery status unavailable")
        page.locator(".delivery-diagnostics summary").click()
        expect(
            page.get_by_text("Counts below are from the last successful check", exact=False)
        ).to_be_visible()
        page.unroute("**/api/health")
        page.get_by_role("button", name="Retry", exact=True).click()
        expect(page.locator(".delivery-diagnostics")).not_to_contain_text(
            "Delivery status unavailable"
        )
        browser.close()
