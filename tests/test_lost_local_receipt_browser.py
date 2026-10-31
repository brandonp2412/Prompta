"""End-to-end local read/pin commits with HTTP acknowledgments deliberately lost."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import Route, expect, sync_playwright
from test_web_results import completed_run, server


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_lost_local_pin_and_read_acknowledgments_reconcile_without_replay(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "receipt-one", "Local receipt probe", time.time() - 20)
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        remote: list[str] = []
        mutations: list[str] = []
        page.on("request", lambda request: remote.append(request.url) if not request.url.startswith(
            f"http://127.0.0.1:{port}/"
        ) else None)
        page.route("**/api/events", lambda route: route.abort())

        def commit_without_ack(route: Route) -> None:
            if route.request.method != "POST":
                route.continue_()
                return
            # Commit once in SQLite, then lose the browser-facing response.
            # Reconciliation may only issue GETs.
            response = route.fetch()
            assert response.status == 200
            mutations.append(route.request.url)
            route.abort()

        page.route("**/api/local-chat-pins", commit_without_ack)
        page.route("**/api/local-chat-reads", commit_without_ack)
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        row = page.locator(".chats-list .chat-entry").filter(has_text="Local receipt probe")
        expect(row).to_be_visible()
        row.get_by_role("button", name="Pin Local receipt probe").click()
        expect(row.get_by_role("button", name="Unpin Local receipt probe")).to_be_visible()
        deadline = time.monotonic() + 5
        while [item["send_id"] for item in app.results.local_pinned_runs()] != ["receipt-one"]:
            assert time.monotonic() < deadline, "Pin was not committed"
            time.sleep(0.05)
        page.wait_for_timeout(200)
        expect(page.get_by_text("Pin change could not be confirmed", exact=False)).to_have_count(0)

        row.get_by_role("button", name="Unpin Local receipt probe").click()
        expect(row.get_by_role("button", name="Pin Local receipt probe")).to_be_visible()
        deadline = time.monotonic() + 5
        while app.results.local_pinned_runs():
            assert time.monotonic() < deadline, "Unpin was not committed"
            time.sleep(0.05)

        row.locator(".chat-row").click()
        expect(page.locator(".chat-transcript-scroll")).to_contain_text("Answer for Local receipt probe")
        deadline = time.monotonic() + 5
        while True:
            record = app.results.detail("receipt-one")
            assert record is not None
            app.replies.annotate_response_markers([record])
            app.results.annotate_local_reads([record])
            if record["last_read_revision"] == record["last_reply_revision"]:
                break
            assert time.monotonic() < deadline, "Read receipt was not committed"
            time.sleep(0.05)
        page.wait_for_timeout(200)
        expect(page.get_by_text("Read status could not be confirmed", exact=False)).to_have_count(0)
        assert len([url for url in mutations if url.endswith("/api/local-chat-pins")]) == 2
        assert len([url for url in mutations if url.endswith("/api/local-chat-reads")]) == 1
        assert remote == []
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_lost_bulk_read_acknowledgment_refreshes_without_a_second_write(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "receipt-bulk", "Bulk read receipt probe", time.time() - 20)
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        writes: list[str] = []
        page.route("**/api/events", lambda route: route.abort())

        def commit_without_ack(route: Route) -> None:
            response = route.fetch()
            assert response.status == 200
            writes.append(route.request.url)
            route.abort()

        page.route("**/api/local-chat-reads/all", commit_without_ack)
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        expect(page.locator(".chats-list")).to_contain_text("Bulk read receipt probe")
        page.get_by_role("button", name="Mark all local chats as read").click()
        expect(page.get_by_text("Mark-all read status could not be confirmed", exact=False)).to_be_visible()
        deadline = time.monotonic() + 5
        while True:
            record = app.results.detail("receipt-bulk")
            assert record is not None
            app.replies.annotate_response_markers([record])
            app.results.annotate_local_reads([record])
            if record["last_read_revision"] == record["last_reply_revision"]:
                break
            assert time.monotonic() < deadline, "Bulk read was not committed"
            time.sleep(0.05)
        assert len(writes) == 1, "Never replay a bulk write after lost acknowledgment"
        browser.close()
