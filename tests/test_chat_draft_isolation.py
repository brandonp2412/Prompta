"""Chat composers never import another run's unsent or saved reply text."""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path

import pytest
from playwright.sync_api import expect, sync_playwright

from prompta.reply_contracts import ReplyIntent
from prompta.response_capture import CaptureResult
from prompta.web import PromptaJobServer


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_prepared_reply_does_not_repopulate_composer_until_preflight_fails(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")

    app = PromptaJobServer(
        ("127.0.0.1", 0),
        state_path=tmp_path / "state.sqlite3",
        jobs_path=tmp_path / "jobs.sqlite3",
    )
    now = time.time()
    send_id = "pending-reply"
    reply_text = "Saved pending reply must not become a draft again"
    app.results.ensure_queued(send_id, "Original completed chat", now=now)
    assert app.results.accept(send_id, "owner", deadline=now + 3000)
    assert app.results.write(
        send_id,
        "owner",
        CaptureResult("sse", "complete", "Original answer", "c" * 32, "m" * 32, "p" * 32),
    )
    assert app.replies.prepare(
        send_id,
        ReplyIntent("r" * 32, "c" * 32, "m" * 32, reply_text),
        now=now + 1,
    )

    thread = threading.Thread(target=app.serve_forever, daemon=True)
    thread.start()
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.goto(f"http://127.0.0.1:{app.server_address[1]}/?view=chats&run={send_id}")
            reply = page.get_by_role("textbox", name="Message for current chat")
            expect(page.get_by_text(reply_text)).to_be_visible()
            expect(reply).to_have_value("")
            page.reload()
            expect(reply).to_have_value("")

            # Only a confirmed preflight failure restores the exact saved
            # text for a deliberate retry; pending work is already durable.
            assert app.replies.mark_preflight_failed("r" * 32)
            page.reload()
            expect(reply).to_have_value(reply_text)
            browser.close()
    finally:
        app.shutdown()
        thread.join(timeout=3)
        app.server_close()


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_chat_drafts_are_scoped_during_spa_navigation_and_reload(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")

    app = PromptaJobServer(
        ("127.0.0.1", 0),
        state_path=tmp_path / "state.sqlite3",
        jobs_path=tmp_path / "jobs.sqlite3",
    )
    now = time.time()
    for send_id, prompt in [("run-a", "Synthetic chat Alpha"), ("run-b", "Synthetic chat Beta")]:
        app.results.ensure_queued(send_id, prompt, now=now)
        assert app.results.accept(send_id, "owner", deadline=now + 3000)
        assert app.results.write(
            send_id,
            "owner",
            CaptureResult(
                "sse", "complete", "Response for " + prompt, "c" * 32, "m" * 32, "p" * 32
            ),
        )
    assert app.replies.prepare(
        "run-a",
        ReplyIntent("r" * 32, "c" * 32, "m" * 32, "Saved exact Alpha reply"),
        now=now + 1,
    )
    assert app.replies.mark_preflight_failed("r" * 32)

    thread = threading.Thread(target=app.serve_forever, daemon=True)
    thread.start()
    seen_posts: list[str] = []
    try:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(executable_path=executable, headless=True)
            page = browser.new_page(viewport={"width": width, "height": height})
            page.on(
                "request",
                lambda request: (
                    seen_posts.append(request.url) if request.method == "POST" else None
                ),
            )
            page.goto(f"http://127.0.0.1:{app.server_address[1]}/?view=chats&run=run-a")
            reply = page.get_by_role("textbox", name="Message for current chat")
            expect(reply).to_have_value("Saved exact Alpha reply")
            reply.fill("Locally edited Alpha only")

            def select(title: str, send_id: str) -> None:
                if width <= 680:
                    page.get_by_role("button", name="Open chat sidebar").click()
                page.locator(".chats-list .chat-row").filter(has_text=title).click()
                page.wait_for_url("**/?view=chats&run=" + send_id)

            # Switching away from a pending reply must not hydrate it into Beta.
            select("Synthetic chat Beta", "run-b")
            expect(reply).to_have_value("")
            reply.fill("Unsent Beta only")
            select("Synthetic chat Alpha", "run-a")
            expect(reply).to_have_value("Locally edited Alpha only")
            select("Synthetic chat Beta", "run-b")
            expect(reply).to_have_value("Unsent Beta only")
            page.reload()
            expect(reply).to_have_value("Unsent Beta only")

            # The fresh-chat draft has a separate namespace from either reply.
            if width <= 680:
                page.get_by_role("button", name="Open chat sidebar").click()
            page.locator(".chats-sidebar .sidebar-primary").click()
            page.wait_for_url("**/?view=chats&draft=new")
            fresh = page.get_by_role("textbox", name="Message for new chat")
            expect(fresh).to_have_value("")
            fresh.fill("Unsent fresh only")
            select("Synthetic chat Beta", "run-b")
            expect(reply).to_have_value("Unsent Beta only")
            select("Synthetic chat Alpha", "run-a")
            expect(reply).to_have_value("Locally edited Alpha only")
            page.reload()
            expect(reply).to_have_value("Locally edited Alpha only")
            if width <= 680:
                page.get_by_role("button", name="Open chat sidebar").click()
            page.locator(".chats-sidebar .sidebar-primary").click()
            expect(fresh).to_have_value("Unsent fresh only")
            # Local read receipts are allowed; navigation must never send a reply.
            assert all(url.endswith("/api/local-chat-reads") for url in seen_posts), seen_posts
            browser.close()
    finally:
        app.shutdown()
        thread.join(timeout=3)
        app.server_close()
