from __future__ import annotations

import asyncio
import os
import shutil

import pytest
from patchright.async_api import async_playwright as async_patchright

import prompta.connector_approval_supervisor as supervisor
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
        active=lambda: True,
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
        active=lambda: True,
    )
    assert result == 0
    assert calls <= 2


@pytest.mark.asyncio
async def test_failed_permission_pipe_backs_off_and_aggregates(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    attempts = 0
    sleeps: list[float] = []
    real_sleep = asyncio.sleep

    async def unavailable(_script: str) -> object:
        nonlocal attempts
        attempts += 1
        try:
            raise RuntimeError("do-not-log-message-or-authentication-data")
        except RuntimeError as cause:
            raise Exception("do-not-log-browser-exception-text") from cause

    async def observe_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(supervisor.asyncio, "sleep", observe_sleep)
    with caplog.at_level("INFO"):
        count = await supervise_connector_approvals(
            unavailable,
            deadline=asyncio.get_running_loop().time() + 60,
            source="test",
            poll_interval_seconds=0.2,
            active=lambda: attempts < 5,
        )
    assert count == 0
    assert attempts == 5
    assert sleeps == [1.0, 2.0, 4.0, 8.0, 16.0]
    assert caplog.text.count("event=connector_approval_check_failed") == 1
    assert caplog.text.count("event=connector_approval_check_unavailable") == 1
    assert "builtins.Exception>builtins.RuntimeError" in caplog.text
    assert "do-not-log" not in caplog.text


@pytest.mark.asyncio
async def test_approval_check_recovery_resets_failure_backoff(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    outcomes = iter(("fail", False, False))
    sleeps: list[float] = []
    real_sleep = asyncio.sleep
    checks = 0

    async def evaluate(_script: str) -> object:
        nonlocal checks
        checks += 1
        outcome = next(outcomes)
        if outcome == "fail":
            raise ConnectionError("connection closed")
        return outcome

    async def observe_sleep(seconds: float) -> None:
        sleeps.append(seconds)
        await real_sleep(0)

    monkeypatch.setattr(supervisor.asyncio, "sleep", observe_sleep)
    with caplog.at_level("INFO"):
        await supervise_connector_approvals(
            evaluate,
            deadline=asyncio.get_running_loop().time() + 30,
            source="test",
            poll_interval_seconds=0.2,
            active=lambda: checks < 3,
        )
    assert sleeps == [1.0, 0.2, 0.2]
    assert "event=connector_approval_check_recovered" in caplog.text
    assert "event=connector_approval_check_unavailable" not in caplog.text


@pytest.mark.asyncio
async def test_trusted_retry_handles_unhydrated_permission_controls() -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM") or shutil.which("chromium")
    if chromium is None:
        pytest.skip("System Chromium is unavailable")
    async with async_patchright() as patchright:
        browser = await patchright.chromium.launch(
            executable_path=chromium, headless=True, args=["--no-sandbox"]
        )
        try:
            page = await browser.new_page()
            await page.set_content(
                "<div role=\"dialog\"><button onclick=\"document.body.dataset.events=(document.body.dataset.events||'')+(event.isTrusted?'T':'F');"
                'if(event.isTrusted)this.parentElement.remove()">Always allow</button>'
                "<button>Allow once</button><button>Deny</button></div>"
            )
            grants = await supervise_connector_approvals(
                page.evaluate,
                deadline=asyncio.get_running_loop().time() + 2.0,
                source="test",
                poll_interval_seconds=0.01,
                active=lambda: True,
                trusted_retry=lambda: trusted_approval_retry(page),
            )
            assert grants == 1
            assert await page.evaluate("document.body.dataset.events") == "FT"
        finally:
            await browser.close()


@pytest.mark.asyncio
async def test_trusted_retry_checks_checkbox_before_grant() -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM") or shutil.which("chromium")
    if chromium is None:
        pytest.skip("System Chromium is unavailable")
    async with async_patchright() as patchright:
        browser = await patchright.chromium.launch(
            executable_path=chromium, headless=True, args=["--no-sandbox"]
        )
        try:
            page = await browser.new_page()
            await page.set_content(
                '<div role="dialog"><label><input type="checkbox" id="persistent">'
                'Always allow</label><button id="confirm" onclick="'
                "if(event.isTrusted){document.body.dataset.approved='true';this.parentElement.remove()}\">"
                "Allow</button></div>"
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
                active=lambda: True,
                trusted_retry=lambda: trusted_approval_retry(page),
            )
            assert grants == 1
            assert await page.evaluate("document.body.dataset.approved") == "true"
        finally:
            await browser.close()
