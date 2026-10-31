from __future__ import annotations

import asyncio
import os
import shutil

import pytest
from playwright.async_api import async_playwright

from prompta.browser_script_loader import load_browser_script
from prompta.connector_approval_supervisor import (
    supervise_connector_approvals,
    trusted_approval_retry,
)


@pytest.mark.asyncio
async def test_shared_supervisor_approves_successive_dialogs_immediately() -> None:
    observed: list[str] = []
    outcomes: list[object] = [True, True, False]

    async def evaluate(script: str) -> object:
        observed.append(script)
        if outcomes:
            return outcomes.pop(0)
        return False

    count = await supervise_connector_approvals(
        evaluate,
        deadline=asyncio.get_running_loop().time() + 0.03,
        source="live",
        poll_interval_seconds=0.01,
    )
    assert count == 2
    assert len(observed) >= 3
    assert all(script == load_browser_script("approve_connector.js") for script in observed)


@pytest.mark.asyncio
async def test_shared_supervisor_stops_if_original_tab_is_gone() -> None:
    calls = 0

    async def evaluate(_script: str) -> object:
        nonlocal calls
        calls += 1
        return True

    result = await supervise_connector_approvals(
        evaluate,
        deadline=asyncio.get_running_loop().time() + 5,
        source="backup",
        poll_interval_seconds=1.0,
        active=lambda: False,
    )
    assert result == 0
    assert calls == 0


@pytest.mark.asyncio
async def test_shared_supervisor_does_not_retry_stuck_dialog_tightly() -> None:
    calls = 0

    async def evaluate(_script: str) -> object:
        nonlocal calls
        calls += 1
        return "stuck"

    result = await supervise_connector_approvals(
        evaluate,
        deadline=asyncio.get_running_loop().time() + 0.025,
        source="live",
        poll_interval_seconds=0.02,
    )
    assert result == 0
    assert calls <= 2


@pytest.mark.asyncio
async def test_trusted_retry_handles_unhydrated_permission_controls() -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM") or shutil.which("chromium")
    if chromium is None:
        pytest.skip("System Chromium is unavailable")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=chromium, headless=True, args=["--no-sandbox"]
        )
        try:
            page = await browser.new_page()
            await page.set_content(
                '<div role="dialog"><button onclick="window.events.push(event.isTrusted);'
                'if(event.isTrusted)this.parentElement.remove()">Always allow</button>'
                '<button>Allow once</button><button>Deny</button></div>'
            )
            await page.evaluate("window.events=[]")
            grants = await supervise_connector_approvals(
                page.evaluate,
                deadline=asyncio.get_running_loop().time() + 2.0,
                source="test",
                poll_interval_seconds=0.01,
                trusted_retry=lambda: trusted_approval_retry(page),
            )
            assert grants == 1
            assert await page.evaluate("window.events") == [False, True]
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_trusted_retry_checks_checkbox_before_grant() -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM") or shutil.which("chromium")
    if chromium is None:
        pytest.skip("System Chromium is unavailable")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=chromium, headless=True, args=["--no-sandbox"]
        )
        try:
            page = await browser.new_page()
            await page.set_content(
                '<div role="dialog"><label><input type="checkbox" id="persistent">'
                'Always allow</label><button id="confirm" onclick="'
                'if(event.isTrusted){window.approved=true;this.parentElement.remove()}">'
                'Allow</button></div>'
            )
            await page.evaluate(
                "document.getElementById('persistent').addEventListener('click', "
                "event => {if(!event.isTrusted)event.preventDefault()})"
            )
            grants = await supervise_connector_approvals(
                page.evaluate,
                deadline=asyncio.get_running_loop().time() + 3.0,
                source="test",
                poll_interval_seconds=0.01,
                trusted_retry=lambda: trusted_approval_retry(page),
            )
            assert grants == 1
            assert await page.evaluate("window.approved === true") is True
        finally:
            await browser.close()
