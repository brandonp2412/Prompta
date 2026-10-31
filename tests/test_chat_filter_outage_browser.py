"""A failed search must not erase an already visible local transcript rail."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from test_web_results import completed_run, server


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_search_failure_keeps_confirmed_chats_until_new_page_arrives(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "stable-visible-run", "Keep visible across outage", time.time())
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        page.route("**/api/events", lambda route: route.abort())
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        row = page.locator(".chats-list .chat-row").filter(has_text="Keep visible across outage")
        expect(row).to_be_visible()
        page.get_by_role("button", name="Search chats").click()
        search = page.locator('input[placeholder="Search chats"]')

        page.route(
            "**/api/results?*",
            lambda route: route.fulfill(status=503, body="Temporary local outage"),
        )
        search.fill("no-such-chat")
        expect(page.get_by_text("Local results are temporarily unavailable.")).to_be_visible()
        expect(row).to_be_visible()
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1")

        page.unroute("**/api/results?*")
        search.fill("Keep visible")
        expect(row).to_be_visible()
        expect(page.get_by_text("Local results are temporarily unavailable.")).to_have_count(0)
        browser.close()
