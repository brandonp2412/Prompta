"""Browser proof for local list refresh consistency and update coalescing."""
from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from web_results_support import completed_run, server

from prompta.response_capture import CaptureResult


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_status_filtered_chat_disappears_after_completion(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        now = time.time()
        app.results.ensure_queued("filtered-local-run", "Filtering probe", now=now)
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        remote: list[str] = []
        page.on("request", lambda request: remote.append(request.url) if not request.url.startswith(
            f"http://127.0.0.1:{port}/"
        ) else None)
        page.route("**/api/events", lambda route: route.abort())
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        page.get_by_role("button", name="Search chats").click()
        page.get_by_label("Filter results by state").select_option("queued")
        expect(page.locator(".chats-list .chat-row").filter(has_text="Filtering probe")).to_be_visible()
        owner = "123:browser-refresh"
        assert app.results.accept("filtered-local-run", owner, deadline=now + 600, now=now + 1)
        assert app.results.write("filtered-local-run", owner, CaptureResult(
            "sse", "complete", "Filtered result finished",
            "12345678-1234-4123-8123-123456789abc",
            "87654321-4321-4321-8321-123456789abc", None,
        ), now=now + 2)
        page.evaluate("window.dispatchEvent(new Event('online'))")
        expect(page.get_by_text("No matching chats")).to_be_visible()
        expect(page.locator(".chats-list .chat-row").filter(has_text="Filtering probe")).to_have_count(0)
        assert remote == []
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_burst_of_reconnect_events_coalesces_slow_chat_reads(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "burst-local-run", "Reconnect probe", time.time())
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
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
