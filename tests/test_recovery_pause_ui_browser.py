"""Recovery bookkeeping stays out of chats without contacting ChatGPT."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import Request, expect
from patchright.sync_api import sync_playwright as sync_patchright
from test_stage5_composer import serve_test_ui

from prompta.response_store import ResponseStore


@pytest.mark.parametrize("width,height", [(1440, 900), (320, 720), (360, 800), (390, 844), (412, 915)])
def test_interrupted_chat_omits_backlog_without_reopening_chatgpt(
    tmp_path: Path,
    width: int,
    height: int,
) -> None:
    executable = os.environ.get("PROMPTA_TEST_CHROMIUM", "")
    if not executable or not Path(executable).exists():
        pytest.skip("Headless Chromium unavailable")
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    now = time.time()
    store.ensure_queued("cooldown", "Private original", now=now)
    assert store.accept("cooldown", "owner", deadline=now + 4000, now=now + 1)
    assert store.bind_conversation_route(
        "cooldown",
        "owner",
        "/c/12345678-1234-4123-8123-123456789abc",
        now=now + 2,
    )
    assert store.finish("cooldown", "owner", "interrupted", now=now + 3)
    with serve_test_ui(tmp_path) as port, sync_patchright() as patchright:
        browser = patchright.chromium.launch(executable_path=executable, headless=True)
        page = browser.new_page(viewport={"width": width, "height": height})
        remote: list[str] = []
        posts: list[str] = []

        def track_request(request: Request) -> None:
            if not request.url.startswith(f"http://127.0.0.1:{port}/"):
                remote.append(request.url)
            if request.method == "POST":
                posts.append(request.url)

        page.on("request", track_request)
        page.route("**/api/events", lambda route: route.abort())
        page.route(
            "**/api/health",
            lambda route: route.fulfill(
                status=200,
                content_type="application/json",
                body='{"ready":true,"recovery":{"account_read_backoff_seconds":600,"security_pause_seconds":0,"global_pace_seconds":0,"recoverable":42,"unresolved_reply_captures":6}}',
            ),
        )
        page.goto(f"http://127.0.0.1:{port}/?view=chats&run=cooldown")
        summary = page.locator(".chat-recovery-guidance p")
        expect(summary).to_have_count(0)
        expect(page.get_by_text("Recovery backlog:")).to_have_count(0)
        expect(page.get_by_role("link", name="Open in ChatGPT", exact=True)).to_have_count(1)
        header_link = page.locator(".workspace-header a.chat-open-chatgpt")
        footer_link = page.locator(".chat-detail-content a.chat-open-chatgpt-footer")
        if width <= 680:
            expect(header_link).to_be_hidden()
            expect(footer_link).to_be_visible()
            assert footer_link.evaluate("(link) => link.parentElement?.lastElementChild === link")
            active_link = footer_link
        else:
            expect(header_link).to_be_visible()
            expect(footer_link).to_be_hidden()
            active_link = header_link
        bounds = active_link.bounding_box()
        assert bounds is not None and 0 <= bounds["x"]
        assert bounds["x"] + bounds["width"] <= width
        expect(page.get_by_role("link", name="Open in ChatGPT", exact=True)).to_have_attribute(
            "href", "https://chatgpt.com/c/12345678-1234-4123-8123-123456789abc",
        )
        assert remote == []
        assert posts == []
        browser.close()
