from __future__ import annotations

import asyncio
import os
import shutil
import socket
import time
from pathlib import Path

import pytest
from playwright.async_api import async_playwright

from prompta.browser_script_loader import load_browser_script


@pytest.mark.asyncio
async def test_browser_composer_focus_rejects_embedded_button_and_focus_steal() -> None:
    chromium = shutil.which("chromium")
    if chromium is None:
        pytest.skip("System Chromium is unavailable")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=chromium, headless=True, args=["--no-sandbox"]
        )
        try:
            page = await browser.new_page()
            await page.set_content(
                '<div id="editor" contenteditable="true">Hello '
                '<span id="text" tabindex="0" contenteditable="true">world</span>'
                '<button id="action" contenteditable="false">Help</button></div>'
                '<button id="popup">Popup</button>'
            )
            editor = page.locator("#editor")
            script = load_browser_script("composer_has_focus.js")
            await page.locator("#text").focus()
            assert await editor.evaluate(script) is True
            await page.locator("#action").focus()
            assert await editor.evaluate(script) is False
            await page.locator("#popup").focus()
            assert await editor.evaluate(script) is False
            await editor.focus()
            assert await editor.evaluate(script) is True
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_connector_permission_controls() -> None:
    chromium = shutil.which("chromium")
    if chromium is None:
        pytest.skip("System Chromium is unavailable")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=chromium, headless=True,
                                                   args=["--no-sandbox"])
        try:
            page = await browser.new_page()
            script = load_browser_script("approve_connector.js")
            await page.set_content('<button onclick="window.clicked=true;this.remove()">Always allow</button>')
            assert await page.evaluate(script) is False
            assert await page.evaluate('window.clicked === true') is False
            await page.set_content('<div role="dialog"><button onclick="window.clicked=true;this.remove()">Always allow</button></div>')
            assert await page.evaluate(script) is True
            assert await page.evaluate('window.clicked') is True
            await page.set_content('<section><button onclick="window.clicked=true;this.remove()">Always allow</button><button>Allow once</button></section>')
            assert await page.evaluate(script) is True
            await page.set_content('<div role="dialog"><label><input type="checkbox">Always allow</label><button onclick="window.checked=document.querySelector(\'input\').checked;this.remove()">Allow</button></div>')
            assert await page.evaluate(script) is True
            assert await page.evaluate('window.checked') is True
            await page.set_content(
                '<div><form><button type="button" onclick="window.approved=true;this.remove()">'
                '<span>Always allow</span></button>'
                '<button>Deny<kbd aria-hidden="true">Esc</kbd></button>'
                '<button><span>Allow once</span><kbd aria-hidden="true">⏎</kbd></button>'
                '</form></div>'
            )
            assert await page.evaluate(script) is True
            assert await page.evaluate('window.approved') is True
            await page.set_content(
                '<div role="dialog" id="first"><button onclick="window.grants=(window.grants||0)+1;'
                'this.parentElement.remove();document.getElementById(\'second\').hidden=false">'
                'Always allow</button></div>'
                '<div role="dialog" id="second" hidden><button onclick="window.grants++;'
                'this.parentElement.remove()">Always allow</button></div>'
            )
            assert await page.evaluate(script) is True
            assert await page.evaluate(script) is True
            assert await page.evaluate(script) is False
            assert await page.evaluate('window.grants') == 2
            await page.set_content(
                '<section><div><div><button aria-labelledby="choice" '
                'onclick="this.remove()"><span id="choice">Always&nbsp; allow</span>'
                '</button></div></div><aside><button>Deny</button></aside></section>'
            )
            assert await page.evaluate(script) is True
            await page.set_content(
                '<div role="dialog"><button onclick="window.attempts=(window.attempts||0)+1">'
                'Always allow</button></div>'
            )
            assert await page.evaluate(script) == "stuck"
            assert await page.evaluate(script) is False
            assert await page.evaluate('window.attempts') == 1
            await page.wait_for_timeout(3000)
            assert await page.evaluate(script) == "stuck"
            await page.wait_for_timeout(3000)
            assert await page.evaluate(script) is False
            assert await page.evaluate('window.attempts') == 2
            await page.set_content(
                '<div role="dialog"><button disabled>Always allow</button>'
                '<button onclick="setTimeout(() => this.remove(), 200)">Always allow</button></div>'
            )
            assert await page.evaluate(script) is True
            await page.set_content(
                '<div role="dialog"><button style="visibility:hidden" '
                'onclick="window.hiddenClicked=true">Always allow</button></div>'
            )
            assert await page.evaluate(script) is False
            assert await page.evaluate('window.hiddenClicked === true') is False
            await page.set_content('<div role="dialog"><button disabled>Always allow</button></div>')
            assert await page.evaluate(script) is False
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_watchdog_reaps_expired_tabs_without_reloading_live_tabs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import prompta.browser_watchdog as watchdog
    from prompta.browser_ownership import (
        MAX_OWNED_TAB_AGE_SECONDS,
        forget_owned_tabs,
        new_owned_window_marker,
        owned_tab_records,
        record_owned_tab,
    )

    chromium = shutil.which("chromium")
    if chromium is None:
        pytest.skip("System Chromium is unavailable")
    ledger = tmp_path / "leases.sqlite3"
    monkeypatch.setattr(watchdog, "owned_tab_records", lambda: owned_tab_records(ledger))
    monkeypatch.setattr(watchdog, "forget_owned_tabs", lambda ids: forget_owned_tabs(ids, ledger))
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            str(tmp_path / "profile"),
            executable_path=chromium,
            headless=True,
            args=["--no-sandbox", f"--remote-debugging-port={port}"],
        )
        try:
            expired = await context.new_page()
            old_marker = new_owned_window_marker(
                now=time.time() - MAX_OWNED_TAB_AGE_SECONDS - 5,
                owner_id=f"{os.getpid()}-test",
            )
            await expired.evaluate("marker => window.name = marker", old_marker)
            hung_lease = await context.new_page()
            session = await context.new_cdp_session(hung_lease)
            try:
                info = await session.send("Target.getTargetInfo")
            finally:
                await session.detach()
            target_id = info["targetInfo"]["targetId"]
            record_owned_tab(target_id, time.time() - MAX_OWNED_TAB_AGE_SECONDS - 5, ledger)
            # The durable target ID must work even without a readable ownership marker.
            await hung_lease.evaluate("window.name = ''")
            recent = await context.new_page()
            await recent.evaluate(
                "marker => window.name = marker",
                new_owned_window_marker(owner_id=f"{os.getpid()}-test"),
            )
            user_tab = await context.new_page()
            await user_tab.evaluate("window.name = 'user-owned'")
            assert await watchdog.reap_expired_owned_tabs(f"127.0.0.1:{port}") == 2
            assert expired.is_closed()
            assert hung_lease.is_closed()
            assert not recent.is_closed()
            assert not user_tab.is_closed()
            assert owned_tab_records(ledger) == {}
            http_expired = await context.new_page()
            session = await context.new_cdp_session(http_expired)
            try:
                http_info = await session.send("Target.getTargetInfo")
            finally:
                await session.detach()
            http_target = http_info["targetInfo"]["targetId"]
            record_owned_tab(http_target, time.time() - MAX_OWNED_TAB_AGE_SECONDS - 5, ledger)
            assert watchdog.reap_expired_leases_http(f"127.0.0.1:{port}") == 1
            await asyncio.sleep(0.1)
            assert http_expired.is_closed()
            assert not user_tab.is_closed()
        finally:
            await context.close()
