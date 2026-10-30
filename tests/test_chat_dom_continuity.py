"""Browser regression: chat navigation and fresh sends preserve existing Svelte DOM."""
from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from prompta.web import PromptaJobServer


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_sidebar_and_reply_composer_keep_identity_through_new_chat(
    tmp_path: Path, width: int, height: int,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    app = PromptaJobServer(
        ("127.0.0.1", 0),
        state_path=tmp_path / "state.sqlite3",
        jobs_path=tmp_path / "jobs.sqlite3",
    )
    for send_id in ("old-alpha", "old-beta"):
        app.results.ensure_queued(send_id, "Synthetic " + send_id, now=time.time())
    thread = threading.Thread(target=app.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=str(chromium), headless=True, args=["--no-sandbox"],
            )
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(f"http://127.0.0.1:{app.server_address[1]}/?view=chats&run=old-alpha")
                expect(page.locator(".chats-list .chat-entry")).to_have_count(2)
                expect(page.get_by_role("textbox", name="Message for current chat")).to_be_visible()
                page.evaluate("""() => {
                    window.__sidebarNode = document.querySelector(".chats-sidebar");
                    window.__rowNode = document.querySelector(".chats-list .chat-entry");
                    window.__composerNode = document.querySelector(".chat-composer-wrap");
                    window.__rowWasRemoved = false;
                    new MutationObserver(() => {
                        if (!window.__rowNode.isConnected) window.__rowWasRemoved = true;
                    }).observe(document.querySelector(".chats-list"), {childList: true, subtree: true});
                }""")

                if width <= 680:
                    page.get_by_role("button", name="Back to chats").click()
                page.locator(".chats-list .chat-row").filter(has_text="Synthetic old-beta").click()
                page.wait_for_url("**/?view=chats&run=old-beta")
                # Desktop preserves the composer through a direct rail switch.
                # Mobile intentionally visits the full-screen list, so the
                # conversation composer is remounted when a chat is reselected.
                if width > 680:
                    assert page.evaluate("""() =>
                        document.querySelector(".chat-composer-wrap") === window.__composerNode
                    """), "Switching between replies remounted the composer"
                else:
                    expect(page.get_by_role("textbox", name="Message for current chat")).to_be_visible()

                if width <= 680:
                    page.get_by_role("button", name="Back to chats").click()
                page.locator(".chats-sidebar .sidebar-primary").click()
                page.wait_for_url("**/?view=chats&draft=new")
                assert page.evaluate("""() =>
                    document.querySelector(".chats-sidebar") === window.__sidebarNode
                """), "New-chat navigation remounted the sidebar"
                assert page.evaluate("() => window.__rowNode.isConnected")

                page.get_by_role("textbox", name="Message for new chat").fill("Synthetic local test")
                with page.expect_response(
                    lambda response: response.url.endswith("/api/chats") and response.request.method == "POST",
                ) as queued:
                    page.get_by_role("button", name="Send fresh chat").click()
                assert queued.value.status == 202
                send_id = queued.value.json()["send_id"]
                page.wait_for_url("**/?view=chats&run=" + send_id)
                expect(page.locator(".chats-list .chat-entry")).to_have_count(3)
                assert page.evaluate("""() =>
                    document.querySelector(".chats-sidebar") === window.__sidebarNode
                    && window.__rowNode.isConnected && !window.__rowWasRemoved
                """), "A confirmed fresh send discarded existing sidebar rows"
            finally:
                browser.close()
    finally:
        app.shutdown()
        thread.join(timeout=3)
        app.server_close()
