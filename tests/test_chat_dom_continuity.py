"""Browser regression: chat navigation and fresh sends preserve existing React DOM."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest
from live_server import LiveServer
from patchright.sync_api import expect, sync_playwright


@pytest.fixture(autouse=True)
def serve_current_worktree_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.web as web_module

    monkeypatch.setattr(web_module, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static")


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_sidebar_and_reply_composer_keep_identity_through_new_chat(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    app = LiveServer(
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
                executable_path=str(chromium),
                headless=True,
                args=["--no-sandbox"],
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
                }""", isolated_context=False)

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
                    """, isolated_context=False), "Switching between replies remounted the composer"
                else:
                    expect(
                        page.get_by_role("textbox", name="Message for current chat")
                    ).to_be_visible()

                if width <= 680:
                    page.get_by_role("button", name="Back to chats").click()
                page.locator(".chats-sidebar .sidebar-primary").click()
                page.wait_for_url("**/?view=chats&draft=new")
                assert page.evaluate("""() =>
                    document.querySelector(".chats-sidebar") === window.__sidebarNode
                """, isolated_context=False), "New-chat navigation remounted the sidebar"
                assert page.evaluate("() => window.__rowNode.isConnected", isolated_context=False)

                composer = page.get_by_role("textbox", name="Message for new chat")
                composer.fill("Synthetic local test")
                page.evaluate("""() => {
                    window.__freshComposerNode = document.querySelector('.chat-composer-wrap');
                    window.__freshTextareaNode = document.querySelector('.chat-composer textarea');
                }""", isolated_context=False)
                with page.expect_response(
                    lambda response: (
                        response.url.endswith("/api/chats") and response.request.method == "POST"
                    ),
                ) as queued:
                    composer.press("Enter")
                assert queued.value.status == 202
                send_id = queued.value.json()["send_id"]
                page.wait_for_url("**/?view=chats&run=" + send_id)
                expect(page.get_by_role("textbox", name="Message for current chat")).to_have_value(
                    ""
                )
                expect(page.locator(".chats-list .chat-entry")).to_have_count(3)
                composer_state = page.evaluate("""() => ({
                    wrapperStable: document.querySelector('.chat-composer-wrap') === window.__freshComposerNode,
                    textareaStable: document.querySelector('.chat-composer textarea') === window.__freshTextareaNode,
                    focused: document.activeElement === window.__freshTextareaNode,
                    activeTag: document.activeElement?.tagName,
                })""", isolated_context=False)
                assert composer_state["wrapperStable"], (
                    f"A fresh send remounted the composer: {composer_state}"
                )
                assert composer_state["textareaStable"], (
                    f"A fresh send replaced the textarea: {composer_state}"
                )
                assert composer_state["focused"], (
                    f"A fresh send blurred the textarea: {composer_state}"
                )
                assert page.evaluate("""() =>
                    localStorage.getItem('prompta.new-chat-draft.v1') === null
                """, isolated_context=False), "The submitted fresh draft was retained after route change"
                assert page.evaluate("""() =>
                    document.querySelector(".chats-sidebar") === window.__sidebarNode
                    && window.__rowNode.isConnected && !window.__rowWasRemoved
                """, isolated_context=False), "A confirmed fresh send discarded existing sidebar rows"
            finally:
                browser.close()
    finally:
        app.shutdown()
        thread.join(timeout=3)
        app.server_close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_multiline_reply_clears_with_smooth_resize_and_keeps_focus(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")
    app = LiveServer(
        ("127.0.0.1", 0),
        state_path=tmp_path / "state.sqlite3",
        jobs_path=tmp_path / "jobs.sqlite3",
    )
    app.results.ensure_queued("waiting", "Original synthetic prompt", now=time.time())
    thread = threading.Thread(target=app.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(
                executable_path=str(chromium),
                headless=True,
                args=["--no-sandbox"],
            )
            try:
                page = browser.new_page(viewport={"width": width, "height": height})
                page.goto(f"http://127.0.0.1:{app.server_address[1]}/?view=chats&run=waiting")
                composer = page.get_by_role("textbox", name="Message for current chat")
                expect(composer).to_be_visible()
                message = "Line one\nLine two\nLine three\nLine four"
                composer.fill(message)
                page.evaluate("""() => {
                    window.__composerCollapse = [];
                    const textarea = document.querySelector('.chat-composer textarea');
                    const original = textarea.animate.bind(textarea);
                    textarea.animate = (frames, options) => {
                        window.__composerCollapse.push({ frames, options });
                        return original(frames, options);
                    };
                    window.__composerNode = textarea;
                }""", isolated_context=False)
                with page.expect_response(
                    lambda response: (
                        response.url.endswith("/reply-queue") and response.request.method == "POST"
                    ),
                ) as queued:
                    composer.press("Enter")
                assert queued.value.status == 202
                expect(composer).to_have_value("")
                page.wait_for_function("() => window.__composerCollapse.length > 0")
                state = page.evaluate("""() => ({
                    sameNode: document.querySelector('.chat-composer textarea') === window.__composerNode,
                    focused: document.activeElement === window.__composerNode,
                    animations: window.__composerCollapse,
                })""", isolated_context=False)
                assert state["sameNode"] and state["focused"], state
                animation = state["animations"][0]
                assert float(animation["frames"][0]["height"].removesuffix("px")) > float(
                    animation["frames"][1]["height"].removesuffix("px")
                ), animation
                assert animation["options"]["duration"] == 160
                expect(page.locator(".message-group.user-group")).to_have_count(2)
                assert page.evaluate("() => document.documentElement.scrollWidth <= innerWidth", isolated_context=False)
            finally:
                browser.close()
    finally:
        app.shutdown()
        thread.join(timeout=3)
        app.server_close()
