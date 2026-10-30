"""Actual browser retries for transient local chat/list/detail/pin failures."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright
from test_web_results import completed_run, server


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_local_recovery_controls_restore_list_pins_detail_and_turns(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")

    with server(tmp_path) as (app, port):
        completed_run(app, "local-recovery-run", "Local recovery probe", time.time())
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            remote: list[str] = []
            page.on("request", lambda request: remote.append(request.url) if not request.url.startswith(
                f"http://127.0.0.1:{port}/"
            ) else None)
            # Keep the test deterministic: an unrelated local SSE invalidation
            # must not heal the intercepted response before Retry is clicked.
            page.route("**/api/events", lambda route: route.abort())
            page.route("**/api/results?*", lambda route: route.fulfill(status=503))
            page.route("**/api/local-chat-pins", lambda route: route.fulfill(status=503))
            page.goto(f"http://127.0.0.1:{port}/?view=chats")
            expect(page.get_by_role("button", name="Retry chats")).to_be_visible()
            expect(page.get_by_text("Chat list temporarily unavailable")).to_be_visible()
            expect(page.get_by_role("button", name="Retry pins")).to_be_visible()

            page.unroute("**/api/results?*")
            page.unroute("**/api/local-chat-pins")
            page.get_by_role("button", name="Retry chats").click()
            page.get_by_role("button", name="Retry pins").click()
            expect(page.locator(".chats-list .chat-row").filter(has_text="Local recovery probe")).to_be_visible()
            expect(page.get_by_role("button", name="Retry pins")).to_have_count(0)

            page.route("**/api/results/local-recovery-run", lambda route: route.fulfill(status=503))
            page.route("**/api/results/local-recovery-run/turns", lambda route: route.fulfill(status=503))
            page.locator(".chats-list .chat-row").filter(has_text="Local recovery probe").click()
            expect(page.get_by_role("button", name="Retry chat")).to_be_visible()
            page.unroute("**/api/results/local-recovery-run")
            page.get_by_role("button", name="Retry chat").click()
            expect(page.get_by_role("button", name="Retry replies")).to_be_visible()
            page.unroute("**/api/results/local-recovery-run/turns")
            page.get_by_role("button", name="Retry replies").click()
            expect(page.get_by_text("Answer for Local recovery probe")).to_be_visible()
            expect(page.get_by_role("button", name="Retry replies")).to_have_count(0)
            assert remote == []
            browser.close()
