from __future__ import annotations

import asyncio
import logging
import os
import shutil
from pathlib import Path

import pytest
from patchright.async_api import Route, async_playwright

from prompta.browser_script_loader import load_browser_script
from prompta.connector_approval_supervisor import (
    ApprovalCounters,
    supervise_connector_approvals,
    trusted_approval_retry,
)
from prompta.playwright_driver import PlaywrightDriver


@pytest.mark.asyncio
async def test_shared_supervisor_approves_successive_dialogs_immediately() -> None:
    observed: list[str] = []
    outcomes: list[object] = [
        {"status": "dismissed", "detected": 1, "allow_clicked": 1, "dismissed": 1},
        {"status": "dismissed", "detected": 1, "allow_clicked": 1, "dismissed": 1},
        {"status": "idle"},
    ]

    async def evaluate(script: str) -> object:
        observed.append(script)
        if outcomes:
            return outcomes.pop(0)
        return {"status": "idle"}

    count = await supervise_connector_approvals(
        evaluate,
        deadline=asyncio.get_running_loop().time() + 0.03,
        source="live",
        poll_interval_seconds=0.01,
        active=lambda: True,
    )
    assert count == ApprovalCounters(detected=2, allow_clicked=2, dismissed=2)
    assert len(observed) >= 3
    assert all(script == load_browser_script("approve_connector.js") for script in observed)


@pytest.mark.asyncio
async def test_shared_supervisor_stops_if_original_tab_is_gone() -> None:
    calls = 0

    async def evaluate(_script: str) -> object:
        nonlocal calls
        calls += 1
        return {"status": "dismissed", "dismissed": 1}

    result = await supervise_connector_approvals(
        evaluate,
        deadline=asyncio.get_running_loop().time() + 5,
        source="live",
        poll_interval_seconds=1.0,
        active=lambda: False,
    )
    assert result == ApprovalCounters()
    assert calls == 0


@pytest.mark.asyncio
async def test_shared_supervisor_does_not_retry_stuck_dialog_tightly() -> None:
    calls = 0

    async def evaluate(_script: str) -> object:
        nonlocal calls
        calls += 1
        return {"status": "stuck", "detected": 1, "allow_clicked": 1}

    result = await supervise_connector_approvals(
        evaluate,
        deadline=asyncio.get_running_loop().time() + 0.025,
        source="live",
        poll_interval_seconds=0.02,
        active=lambda: True,
    )
    assert result.timeout_failure >= 1
    assert result.dismissed == 0
    assert calls <= 2


@pytest.mark.asyncio
async def test_ownership_revoked_during_check_prevents_trusted_click() -> None:
    owned = True
    trusted_calls = 0

    async def evaluate(_script: str) -> object:
        nonlocal owned
        owned = False
        return {"status": "stuck", "detected": 1, "allow_clicked": 1}

    async def trusted() -> object:
        nonlocal trusted_calls
        trusted_calls += 1
        return {"status": "dismissed"}

    counts = await supervise_connector_approvals(
        evaluate,
        deadline=asyncio.get_running_loop().time() + 1.0,
        source="live",
        poll_interval_seconds=0.01,
        active=lambda: owned,
        trusted_retry=trusted,
    )
    assert counts == ApprovalCounters(detected=1, allow_clicked=1, timeout_failure=1)
    assert trusted_calls == 0


@pytest.mark.asyncio
async def test_approval_failures_never_log_dialog_content(
    caplog: pytest.LogCaptureFixture,
) -> None:
    async def evaluate(_script: str) -> object:
        raise RuntimeError("secret dialog content")

    with caplog.at_level(logging.INFO):
        counts = await supervise_connector_approvals(
            evaluate,
            deadline=asyncio.get_running_loop().time() + 0.02,
            source="live",
            poll_interval_seconds=0.01,
            active=lambda: True,
        )
    assert counts.timeout_failure >= 1
    assert "secret dialog content" not in caplog.text
    assert "error_type=RuntimeError" in caplog.text


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
            await page.evaluate('window.name = "prompta-delivery:1761990000:test:1234abcd"')
            await page.set_content(
                '<div role="dialog"><button onclick="document.body.dataset.events=(document.body.dataset.events||\'\')+(event.isTrusted?\'T\':\'F\');'
                'if(event.isTrusted)this.parentElement.remove()">Always allow</button>'
                '<button>Allow once</button><button>Deny</button></div>'
            )
            grants = await supervise_connector_approvals(
                page.evaluate,
                deadline=asyncio.get_running_loop().time() + 2.0,
                source="test",
                poll_interval_seconds=0.01,
                active=lambda: not page.is_closed(),
                trusted_retry=lambda: trusted_approval_retry(page, active=lambda: not page.is_closed()),
            )
            assert grants.dismissed == 1
            assert grants.detected == 1
            assert grants.allow_clicked == 2
            assert await page.evaluate("document.body.dataset.events") == "FT"
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
            await page.evaluate('window.name = "prompta-delivery:1761990000:test:1234abcd"')
            await page.set_content(
                '<div role="dialog"><label><input type="checkbox" id="persistent">'
                'Always allow</label><button id="confirm" onclick="'
                'if(event.isTrusted){document.body.dataset.approved=\'true\';this.parentElement.remove()}">'
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
                active=lambda: not page.is_closed(),
                trusted_retry=lambda: trusted_approval_retry(page, active=lambda: not page.is_closed()),
            )
            assert grants.dismissed == 1
            assert grants.persistent_selected == 1
            assert await page.evaluate("document.body.dataset.approved") == "true"
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_owned_tab_approval_e2e_and_non_owned_tab_remains_untouched(tmp_path: Path) -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM") or shutil.which("chromium")
    if chromium is None:
        pytest.skip("System Chromium is unavailable")
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(
            executable_path=chromium, headless=True, args=["--no-sandbox"]
        )
        try:
            owned = await browser.new_page()
            other = await browser.new_page()

            async def fixture(route: Route) -> None:
                await route.fulfill(
                    status=200,
                    content_type="text/html",
                    body='<div role="dialog"><button onclick="document.body.dataset.clicked=\'yes\';this.parentElement.remove()">Always allow</button></div>',
                )

            await owned.route("https://chatgpt.com/**", fixture)
            await other.route("https://chatgpt.com/**", fixture)
            await owned.goto("https://chatgpt.com/c/11111111-1111-4111-8111-111111111111")
            await other.goto("https://chatgpt.com/c/22222222-2222-4222-8222-222222222222")
            await owned.evaluate('window.name = "prompta-delivery:1761990000:test:1234abcd"')
            driver = PlaywrightDriver(profile=tmp_path)
            driver._connected = True
            driver.context = "owned"
            driver._pages["owned"] = owned
            driver._owned_contexts.add("owned")
            driver._owned_target_ids["owned"] = "fixture-target"
            assert driver.approval_tab_active
            counts = await supervise_connector_approvals(
                driver.eval,
                deadline=asyncio.get_running_loop().time() + 0.5,
                source="live",
                poll_interval_seconds=0.01,
                active=lambda: driver.approval_tab_active,
                trusted_retry=driver.click_stuck_connector_approval,
            )
            assert counts == ApprovalCounters(detected=1, allow_clicked=1, dismissed=1)
            assert await owned.evaluate("document.body.dataset.clicked") == "yes"
            assert await other.evaluate("document.body.dataset.clicked || null") is None
            driver._owned_contexts.clear()
            assert not driver.approval_tab_active
            assert await driver.click_stuck_connector_approval() == {"status": "idle"}
        finally:
            await browser.close()
