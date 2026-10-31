"""Actual browser retries for transient local chat/list/detail/pin failures."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from web_results_support import completed_run, server


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

            # Exercise Retry while the injected outage is still active. If the
            # route is removed first, a background refresh may already have
            # restored the view and detached the button before Playwright clicks.
            page.get_by_role("button", name="Retry pins").click()
            expect(page.get_by_role("button", name="Retry pins")).to_be_visible()
            page.unroute("**/api/results?*")
            page.unroute("**/api/local-chat-pins")
            page.evaluate("window.dispatchEvent(new Event('online'))")
            expect(page.locator(".chats-list .chat-row").filter(has_text="Local recovery probe")).to_be_visible()
            expect(page.get_by_role("button", name="Retry chats")).to_have_count(0)
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
            expect(page.locator(".chat-transcript-scroll").get_by_text("Answer for Local recovery probe")).to_be_visible()
            expect(page.get_by_role("button", name="Retry replies")).to_have_count(0)
            assert remote == []
            browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_retry_chats_recovers_list_without_a_pin_failure(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "list-only-outage", "List-only recovery probe", time.time())
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        posts: list[str] = []
        page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
        page.route("**/api/events", lambda route: route.abort())
        page.route("**/api/results?*", lambda route: route.fulfill(status=503))
        # Complete the independent pins request before repairing the list.
        with page.expect_response(lambda response: "/api/local-chat-pins" in response.url):
            page.goto(f"http://127.0.0.1:{port}/?view=chats")
        expect(page.get_by_role("button", name="Retry chats")).to_be_visible()
        # Click before lifting the failure, then prove the reconnect repairs
        # the list even if another refresh starts as soon as the outage ends.
        page.get_by_role("button", name="Retry chats").click()
        expect(page.get_by_role("button", name="Retry chats")).to_be_visible()
        page.unroute("**/api/results?*")
        page.evaluate("window.dispatchEvent(new Event('online'))")
        expect(page.locator(".chats-list .chat-row").filter(has_text="List-only recovery probe")).to_be_visible()
        expect(page.get_by_role("button", name="Retry chats")).to_have_count(0)
        assert posts == []
        browser.close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_retry_older_chats_retries_failed_page_without_resetting_list(
    tmp_path: Path, width: int, height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        now = time.time()
        for index in range(25):
            completed_run(app, f"older-page-{index}", f"Older page {index}", now - index)
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        posts: list[str] = []
        page.on("request", lambda request: posts.append(request.url) if request.method == "POST" else None)
        page.route("**/api/events", lambda route: route.abort())
        attempts = [0]

        def older_page_response(route) -> None:
            attempts[0] += 1
            if attempts[0] == 1:
                route.fulfill(status=503)
            else:
                route.continue_()

        page.route("**/api/results?*offset=20*", older_page_response)
        page.goto(f"http://127.0.0.1:{port}/?view=chats")
        expect(page.locator(".chats-list .chat-entry")).to_have_count(20)
        page.locator(".chats-list").evaluate("node => node.scrollTop = node.scrollHeight")
        # Scrolling may immediately trigger a second fetch after the injected
        # 503, so either the retry control or the recovered page is valid.
        page.wait_for_function("""() =>
            document.querySelectorAll('.chats-list .chat-entry').length === 25 ||
            [...document.querySelectorAll('button')].some(
                button => button.textContent?.trim() === 'Retry older chats'
            )
        """)
        # A narrow viewport can trigger an automatic second fetch while the
        # sidebar scroll settles. Click the retry if still present; either
        # recovery path must restore the older page without another POST.
        page.evaluate("""() => {
            const button = [...document.querySelectorAll('button')]
                .find(item => item.textContent?.trim() === 'Retry older chats');
            button?.click();
        }""")
        expect(page.locator(".chats-list .chat-entry")).to_have_count(25)
        assert attempts[0] >= 2
        expect(page.get_by_role("button", name="Retry older chats")).to_have_count(0)
        assert posts == []
        browser.close()
