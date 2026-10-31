"""Isolated Chromium regression for ownership-only watchdog expiry."""

from __future__ import annotations

import asyncio
import socket
import time

import pytest
from patchright.async_api import async_playwright

import prompta.browser_watchdog as watchdog
from prompta.browser_ownership import (
    claim_expired_tab,
    forget_owned_tabs,
    owned_tab_records,
    record_owned_tab,
)


@pytest.mark.asyncio
async def test_crash_reaper_preserves_unowned_and_recent_browser_pages(monkeypatch, tmp_path) -> None:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]

    ledger = tmp_path / "owned.sqlite3"
    monkeypatch.setattr(watchdog, "owned_tab_records", lambda: owned_tab_records(ledger))
    monkeypatch.setattr(watchdog, "forget_owned_tabs", lambda ids: forget_owned_tabs(ids, ledger))
    monkeypatch.setattr(
        watchdog,
        "claim_expired_tab",
        lambda target, cutoff: claim_expired_tab(target, cutoff, ledger),
    )

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(tmp_path / "chromium-profile"),
            headless=True,
            args=[f"--remote-debugging-port={port}", "--no-first-run"],
        )
        try:
            expired = await context.new_page()
            recent = await context.new_page()
            unowned = await context.new_page()
            await asyncio.gather(
                expired.goto("data:text/html,<title>expired</title>"),
                recent.goto("data:text/html,<title>recent</title>"),
                unowned.goto("data:text/html,<title>unowned</title>"),
            )

            async def target_id(page) -> str:
                session = await context.new_cdp_session(page)
                try:
                    info = await session.send("Target.getTargetInfo")
                    target_info = info.get("targetInfo")
                    assert isinstance(target_info, dict)
                    target_id = target_info.get("targetId")
                    assert isinstance(target_id, str)
                    return target_id
                finally:
                    await session.detach()

            now = time.time()
            record_owned_tab(await target_id(expired), now - 2701, ledger)
            record_owned_tab(await target_id(recent), now - 2699, ledger)
            assert await watchdog.reap_expired_owned_tabs(
                address=f"127.0.0.1:{port}", now=now,
            ) == 1
            for _ in range(20):
                if expired.is_closed():
                    break
                await asyncio.sleep(0.05)
            assert expired.is_closed()
            assert not recent.is_closed()
            assert not unowned.is_closed()
            assert len(owned_tab_records(ledger)) == 1
        finally:
            await context.close()
