"""Browser proof for local list refresh consistency and update coalescing."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import expect
from patchright.sync_api import sync_playwright as sync_patchright
from web_results_support import completed_run, server

from prompta.response_capture import CaptureResult


def test_recovery_update_does_not_reorder_sidebar_but_user_followup_does(tmp_path: Path) -> None:
    from sqlalchemy import update

    from prompta.response_store import results as result_table

    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    now = time.time()
    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        completed_run(app, "old-run", "Old chat", now - 500)
        completed_run(app, "new-run", "New chat", now - 100)
        with app.results.engine.begin() as connection:
            connection.execute(
                update(result_table)
                .where(result_table.c.send_id == "old-run")
                .values(updated_at=now, source="history_dom")
            )
        browser = patchright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": 1440, "height": 900})
        page.route("**/api/events", lambda route: route.abort())
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        rows = page.locator(".chats-list .chat-row")
        expect(rows).to_have_count(2)
        expect(rows.first).to_contain_text("New chat")

        app.replies.queue_followup("old-run", "sidebar-followup-001", "Follow-up", now=now + 1)
        page.evaluate("window.dispatchEvent(new Event('online'))")
        expect(rows.first).to_contain_text("Old chat")
        browser.close()


@pytest.mark.parametrize("width,height", [(320, 700), (360, 800), (390, 844), (412, 915), (844, 390), (1440, 900)])
def test_search_keeps_matching_chat_after_status_changes(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        now = time.time()
        app.results.ensure_queued("filtered-local-run", "Filtering probe", now=now)
        browser = patchright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        remote: list[str] = []
        page.on("request", lambda request: remote.append(request.url) if not request.url.startswith(
            f"http://127.0.0.1:{port}/"
        ) else None)
        page.route("**/api/events", lambda route: route.abort())
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        page.get_by_role("button", name="Search chats").click()
        expect(page.get_by_role("combobox", name="Filter results by state")).to_have_count(0)
        search = page.get_by_role("searchbox", name="Search chats")
        controls = page.locator(".chats-controls").bounding_box()
        search_box = search.bounding_box()
        assert controls is not None and search_box is not None
        assert search_box["width"] >= controls["width"] - 25
        search.fill("no-such-chat")
        expect(page.get_by_text("No matching chats")).to_be_visible()
        search.fill("Filtering")
        expect(page.locator(".chats-list .chat-row").filter(has_text="Filtering probe")).to_be_visible()
        owner = "123:browser-refresh"
        assert app.results.accept("filtered-local-run", owner, deadline=now + 600, now=now + 1)
        assert app.results.write("filtered-local-run", owner, CaptureResult(
            "sse", "complete", "Filtered result finished",
            "12345678-1234-4123-8123-123456789abc",
            "87654321-4321-4321-8321-123456789abc", None,
        ), now=now + 2)
        page.evaluate("window.dispatchEvent(new Event('online'))")
        expect(page.locator(".chats-list .chat-row").filter(has_text="Filtering probe")).to_be_visible()
        expect(search).to_have_value("Filtering")
        assert remote == []
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_burst_of_reconnect_events_coalesces_slow_chat_reads(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_patchright() as patchright:
        completed_run(app, "burst-local-run", "Reconnect probe", time.time())
        browser = patchright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        posts: list[str] = []
        page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
        page.route("**/api/events", lambda route: route.abort())
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        expect(page.locator(".chats-list .chat-row").filter(has_text="Reconnect probe")).to_be_visible()
        page.evaluate("""() => {
            window.__listFetchCount = 0;
            const originalFetch = window.fetch.bind(window);
            window.fetch = (resource, options) => {
              if (String(resource).includes("/api/results?")) {
                window.__listFetchCount++;
                return new Promise((resolve) => setTimeout(
                  () => resolve(originalFetch(resource, options)), 1100));
              }
              return originalFetch(resource, options);
            };
            let fired = 0;
            const timer = setInterval(() => {
              window.dispatchEvent(new Event("online"));
              if (++fired === 7) clearInterval(timer);
            }, 160);
        }""")
        page.wait_for_timeout(3000)
        # One request can finish as the final event arrives; allow a third
        # reconciliation but never one fetch for each of the seven events.
        assert page.evaluate("window.__listFetchCount") <= 3
        expect(page.locator(".chats-list .chat-row").filter(has_text="Reconnect probe")).to_be_visible()
        assert posts == []
        browser.close()
