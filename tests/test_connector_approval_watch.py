from __future__ import annotations

import os
import shutil

import pytest
from playwright.async_api import Browser, BrowserContext, Route, async_playwright

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

    # This fixture verifies an opt-in watcher regardless of the host's config.
    monkeypatch.setattr(
        watcher.ConnectorApproval, "load",
        classmethod(lambda cls: cls(enabled=True)),
    )

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

    async def no_open_chat_candidates(_context: object, _excluded: object) -> list[object]:
        return []

    monkeypatch.setattr(watcher, "open_chat_candidates", no_open_chat_candidates)
    await watcher.watch_sidebar(object.__new__(Browser), object.__new__(BrowserContext))
    assert sidebar.closed
    assert chat.closed
    assert chat.url == "https://chatgpt.com" + CHAT_A
    assert chat.grants == 1


@pytest.mark.asyncio
async def test_open_non_prompta_tabs_get_backup_permission_without_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import prompta.connector_approval_watch as watcher

    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM") or shutil.which("chromium")
    if chromium is None:
        pytest.skip("System Chromium is unavailable")

    async def fixture(route: Route) -> None:
        await route.fulfill(
            status=200,
            content_type="text/html",
            body='<div role="dialog"><button onclick="window.grants=(window.grants||0)+1;'
                 'this.parentElement.remove()">Always allow</button><button>Allow once</button></div>',
        )

    monkeypatch.setattr(watcher.ConnectorApproval, "load", lambda: watcher.ConnectorApproval(True))
    monkeypatch.setattr(watcher, "MAX_OWNED_TAB_AGE_SECONDS", 0.5)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=chromium, headless=True, args=["--no-sandbox"]
        )
        try:
            context = await browser.new_context()
            await context.route("https://chatgpt.com/c/**", fixture)
            user_page = await context.new_page()
            await user_page.goto("https://chatgpt.com" + CHAT_A)
            owned_page = await context.new_page()
            await owned_page.goto("https://chatgpt.com" + CHAT_B)
            await owned_page.evaluate("window.name='prompta-delivery:123:owner:tab'")
            candidates = await watcher.open_chat_candidates(context, set())
            assert candidates == [(user_page, CHAT_A)]
            await watcher.watch_open_chat(user_page, CHAT_A)
            assert await user_page.evaluate("window.grants") == 1
            assert not user_page.is_closed()
            assert user_page.url == "https://chatgpt.com" + CHAT_A
            assert await owned_page.evaluate("window.grants || 0") == 0
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_unread_sidebar_detection_and_connector_approval() -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM") or shutil.which("chromium")
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
