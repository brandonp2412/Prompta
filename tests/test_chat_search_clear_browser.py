"""The chat search clear control preserves focus and restores the local list."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
from patchright.sync_api import expect, sync_playwright
from web_results_support import completed_run, server


@pytest.fixture(autouse=True)
def use_worktree_assets(monkeypatch: pytest.MonkeyPatch) -> None:
    import prompta.web as web

    monkeypatch.setattr(web, "_STATIC_ROOT", Path(__file__).resolve().parents[1] / "src/static")


@pytest.mark.parametrize("width,height", [(320, 720), (390, 844), (1440, 900)])
def test_clear_chat_search_restores_results_and_focus(
    tmp_path: Path, width: int, height: int,
) -> None:
    chromium = Path(os.environ.get("PROMPTA_TEST_CHROMIUM", "/usr/bin/chromium"))
    if not chromium.is_file():
        pytest.skip("Chromium unavailable")

    with server(tmp_path) as (app, port), sync_playwright() as playwright:
        completed_run(app, "search-alpha", "Alpha Local Chat", 100)
        completed_run(app, "search-beta", "Beta Local Chat", 200)
        browser = playwright.chromium.launch(
            executable_path=str(chromium), headless=True, args=["--no-sandbox"],
        )
        try:
            page = browser.new_page(viewport={"width": width, "height": height})
            page.route("**/api/events", lambda route: route.abort())
            external_posts: list[str] = []
            page.on("request", lambda request: external_posts.append(request.url)
                    if request.method == "POST" and not request.url.startswith(
                        f"http://127.0.0.1:{port}/"
                    ) else None)
            page.goto(f"http://127.0.0.1:{port}/?view=chats")
            page.get_by_role("button", name="Search chats").click()
            search = page.get_by_role("searchbox", name="Search chats")
            search.fill("Alpha")
            expect(page.locator(".chats-list .chat-row").filter(has_text="Alpha Local Chat")).to_be_visible()
            expect(page.locator(".chats-list .chat-row").filter(has_text="Beta Local Chat")).to_have_count(0)
            clear = page.get_by_role("button", name="Clear chat search")
            expect(clear).to_be_visible()
            clear.click()
            expect(search).to_have_value("")
            assert search.evaluate("(element) => document.activeElement === element")
            expect(page.locator(".chats-list .chat-row").filter(has_text="Alpha Local Chat")).to_be_visible()
            expect(page.locator(".chats-list .chat-row").filter(has_text="Beta Local Chat")).to_be_visible()
            expect(clear).to_have_count(0)
            assert external_posts == []
        finally:
            browser.close()
