"""Approval backup never confuses a rate-limited or failed tab with a loaded chat."""

from __future__ import annotations

import os
import shutil

import pytest
from patchright.async_api import Browser, BrowserContext, Page, Route, async_playwright

import prompta.connector_approval_watch as watcher
from prompta.account_read_gate import AccountReadGate

CHAT = "/c/11111111-1111-4111-8111-111111111111"


class FakeReadGate(AccountReadGate):
    def __init__(self) -> None:
        self.block_seconds = 0.0
        self.events: list[str | None] = []

    def remaining(self) -> float:
        return self.block_seconds

    def note_http_429(self, retry_after_header: str | None = None) -> float:
        self.events.append(retry_after_header)
        self.block_seconds = 300.0
        return self.block_seconds


@pytest.mark.asyncio
async def test_blocked_account_opens_no_chat_tabs(monkeypatch: pytest.MonkeyPatch) -> None:
    gate = FakeReadGate()
    gate.block_seconds = 300.0
    opened = False

    async def fake_wait(_gate: object) -> bool:
        return False

    async def fake_background_page(_browser: object, _context: object) -> None:
        nonlocal opened
        opened = True

    monkeypatch.setattr(watcher, "wait_for_account_read", fake_wait)
    monkeypatch.setattr(watcher, "background_page", fake_background_page)
    assert await watcher.watch_chat(object.__new__(Browser), object.__new__(BrowserContext), CHAT, gate=gate) is False  # type: ignore[arg-type]
    assert not opened


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "expected_events"),
    [
        (429, "<main><div role='region'>Could not load this ChatGPT conversation</div></main>", 1),
        (200, "<main><div role='region'>Could not load this ChatGPT conversation</div></main>", 0),
    ],
)
async def test_rate_limited_or_failed_load_is_not_a_successful_approval_watch(
    monkeypatch: pytest.MonkeyPatch, status: int, body: str, expected_events: int
) -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM") or shutil.which("chromium")
    if not chromium:
        pytest.skip("Chromium unavailable")
    gate = FakeReadGate()
    monkeypatch.setattr(watcher.ConnectorApproval, "load", lambda: watcher.ConnectorApproval(enabled=True))

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=chromium, headless=True, args=["--no-sandbox"]
        )
        try:
            context = await browser.new_context()

            async def fixture(route: Route) -> None:
                await route.fulfill(
                    status=status,
                    content_type="text/html",
                    headers={"retry-after": "360"} if status == 429 else {},
                    body=body,
                )

            await context.route("https://chatgpt.com/c/**", fixture)
            pages: list[Page] = []

            async def new_page(_browser: Browser, _context: BrowserContext) -> Page:
                page = await context.new_page()
                pages.append(page)
                return page

            monkeypatch.setattr(watcher, "background_page", new_page)
            succeeded = await watcher.watch_chat(browser, context, CHAT, gate=gate)
            assert succeeded is False
            assert len(gate.events) == expected_events
            if status == 429:
                assert gate.remaining() == 300
            assert all(page.is_closed() for page in pages)
        finally:
            await browser.close()
