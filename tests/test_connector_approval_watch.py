from __future__ import annotations

import shutil

import pytest
from playwright.async_api import Browser, BrowserContext, async_playwright

from prompta.browser_script_loader import load_browser_script
from prompta.connector_approval_watch import unread_chat_paths

CHAT_A = "/c/11111111-1111-4111-8111-111111111111"
CHAT_B = "/c/22222222-2222-4222-8222-222222222222"


def test_unread_chat_paths_accepts_only_exact_chat_routes() -> None:
    assert unread_chat_paths([CHAT_A, CHAT_A, "/c/anything", CHAT_B + "?x=1", 3, CHAT_B]) == [
        CHAT_A,
        CHAT_B,
    ]
    assert unread_chat_paths("not a list") == []


@pytest.mark.asyncio
async def test_background_watcher_opens_unread_chat_and_grants_permission(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import prompta.connector_approval_watch as watcher

    class Sidebar:
        def __init__(self) -> None:
            self.closed = False
            self.scans = 0

        async def goto(self, _url: str, **_kwargs: object) -> None:
            return None

        async def evaluate(self, _script: str) -> list[str]:
            self.scans += 1
            if self.scans > 1:
                self.closed = True
                return []
            return [CHAT_A]

        def is_closed(self) -> bool:
            return self.closed

        async def close(self) -> None:
            self.closed = True

    class Chat:
        def __init__(self) -> None:
            self.closed = False
            self.url = ""
            self.grants = 0

        async def goto(self, url: str, **_kwargs: object) -> None:
            self.url = url

        async def evaluate(self, _script: str) -> bool:
            if self.grants == 0:
                self.grants += 1
                return True
            return False

        def is_closed(self) -> bool:
            return self.closed

        async def close(self) -> None:
            self.closed = True

    sidebar = Sidebar()
    chat = Chat()
    pages = iter([sidebar, chat])

    async def fake_background_page(_browser: object, _context: object) -> Sidebar | Chat:
        return next(pages)

    monkeypatch.setattr(watcher, "background_page", fake_background_page)
    monkeypatch.setattr(watcher, "_SCAN_INTERVAL_SECONDS", 0.05)
    await watcher.watch_sidebar(object.__new__(Browser), object.__new__(BrowserContext))
    assert sidebar.closed
    assert chat.closed
    assert chat.url == "https://chatgpt.com" + CHAT_A
    assert chat.grants == 1


@pytest.mark.asyncio
async def test_unread_sidebar_detection_and_connector_approval() -> None:
    chromium = shutil.which("chromium")
    if not chromium:
        pytest.skip("System Chromium is unavailable")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=chromium, headless=True, args=["--no-sandbox"]
        )
        try:
            page = await browser.new_page()
            await page.set_content(
                f'<nav>'
                f'<div data-sidebar-cycle-item><a href="{CHAT_A}">Unread UI regression</a>'
                '<button aria-label="Mark as unread" data-testid="mark-unread">Menu</button></div>'
                f'<div data-sidebar-cycle-item data-unread="false"><a href="{CHAT_B}">Read</a></div>'
                '</nav>'
            )
            scan = load_browser_script("find_unread_chats.js")
            assert await page.evaluate(scan) == []

            await page.locator(f'a[href="{CHAT_A}"]').evaluate(
                "(el) => el.parentElement.setAttribute('data-unread', 'true')"
            )
            assert await page.evaluate(scan) == [CHAT_A]

            await page.locator(f'a[href="{CHAT_A}"]').evaluate(
                "(el) => el.parentElement.removeAttribute('data-unread')"
            )
            await page.locator(f'a[href="{CHAT_B}"]').evaluate(
                "(el) => el.parentElement.insertAdjacentHTML('beforeend', "
                "'<span aria-label=\\'Unread response\\'></span>')"
            )
            assert await page.evaluate(scan) == [CHAT_B]

            await page.set_content(
                '<div role="dialog"><button onclick="window.grants=(window.grants||0)+1;'
                'this.parentElement.remove()">Always allow</button></div>'
            )
            assert await page.evaluate(load_browser_script("approve_connector.js")) is True
            assert await page.evaluate("window.grants") == 1
        finally:
            await browser.close()
