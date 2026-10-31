"""Recovery UI explains the persisted read cooldown without contacting ChatGPT."""

from __future__ import annotations

import os
import time
from pathlib import Path

import pytest
from patchright.sync_api import Request, expect, sync_playwright
from test_stage5_composer import serve_test_ui

from prompta.response_store import ResponseStore


@pytest.mark.parametrize("width,height", [(1440, 900), (390, 844)])
def test_interrupted_chat_shows_read_backoff_without_reopening_chatgpt(
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
    with serve_test_ui(tmp_path) as port, sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
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
                body='{"ready":true,"recovery":{"account_read_backoff_seconds":600,"security_pause_seconds":0,"global_pace_seconds":0}}',
            ),
        )
        page.goto(f"http://127.0.0.1:{port}/?view=chats&run=cooldown")
        expect(page.get_by_text("Recovery is waiting about 10 min", exact=False)).to_be_visible()
        expect(page.get_by_text("account read cooldown", exact=False)).to_be_visible()
        expect(page.get_by_role("link", name="Open exact chat in ChatGPT")).to_be_visible()
        assert remote == []
        assert posts == []
        browser.close()
