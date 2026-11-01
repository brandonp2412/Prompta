from __future__ import annotations

import asyncio
import os
import shutil
import socket
import subprocess
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

import pytest
from patchright.async_api import async_playwright as async_patchright

from prompta.browser_ownership import new_owned_window_marker
from prompta.browser_script_loader import load_browser_script
from prompta.connector_approval_supervisor import (
    supervise_connector_approvals,
    trusted_approval_retry,
)
from prompta.patchright_driver import PatchrightDriver


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
async def test_broken_live_channel_uses_independent_owned_tab_retry() -> None:
    primary_calls = 0
    fallback_calls = 0

    async def broken_channel(_script: str) -> object:
        nonlocal primary_calls
        primary_calls += 1
        raise RuntimeError("original page channel is stale")

    async def fresh_owned_tab() -> object:
        nonlocal fallback_calls
        fallback_calls += 1
        return True

    grants = await supervise_connector_approvals(
        broken_channel,
        deadline=asyncio.get_running_loop().time() + 1.65,
        source="test",
        poll_interval_seconds=0.01,
        active=lambda: True,
        fresh_retry=fresh_owned_tab,
    )
    assert grants == 1
    assert fallback_calls == 1
    assert 3 <= primary_calls <= 6


@pytest.mark.asyncio
async def test_failed_fresh_retry_never_claims_an_approval() -> None:
    async def broken_channel(_script: str) -> object:
        raise RuntimeError("original page channel is stale")

    grants = await supervise_connector_approvals(
        broken_channel,
        deadline=asyncio.get_running_loop().time() + 1.65,
        source="test",
        poll_interval_seconds=0.01,
        active=lambda: True,
        fresh_retry=lambda: asyncio.sleep(0, result=False),
    )
    assert grants == 0


@pytest.mark.asyncio
async def test_fresh_retry_requires_an_active_owned_capture(tmp_path: Path) -> None:
    driver = PatchrightDriver(
        profile=tmp_path, debugger_address="127.0.0.1:9222",
        ownership_prefix="prompta-delivery:",
    )
    assert await driver.retry_connector_approval_from_owned_tab() is False
    driver._send_capture = {}
    assert await driver.retry_connector_approval_from_owned_tab() is False


@pytest.mark.asyncio
async def test_fresh_approval_attachment_verifies_exact_target_and_owner(tmp_path: Path) -> None:
    chromium = os.environ.get("PROMPTA_TEST_CHROMIUM") or shutil.which("chromium")
    if chromium is None:
        pytest.skip("System Chromium is unavailable")
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    process = subprocess.Popen(
        [chromium, "--headless=new", "--no-sandbox", "--disable-gpu",
         f"--remote-debugging-port={port}",
         f"--user-data-dir={tmp_path / 'isolated-browser'}", "about:blank"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    address = f"127.0.0.1:{port}"
    try:
        for _ in range(60):
            try:
                with urlopen(f"http://{address}/json/version", timeout=0.2):
                    break
            except (OSError, URLError):
                await asyncio.sleep(0.1)
        else:
            pytest.fail("Isolated CDP browser did not start")

        async with async_patchright() as patchright:
            browser = await patchright.chromium.connect_over_cdp(f"http://{address}")
            context = browser.contexts[0]
            await context.route(
                "https://chatgpt.com/c/**",
                lambda route: route.fulfill(
                    status=200, content_type="text/html",
                    body='<main><div role="dialog" id="permission">'
                    '<button id="grant">Always allow</button>'
                    '<button>Allow once</button><button>Deny</button></div></main>',
                ),
            )
            page = await context.new_page()
            await page.goto("https://chatgpt.com/c/12345678-1234-4123-8123-123456789abc")
            await page.evaluate("""() => {
                window.__grants = 0;
                document.getElementById('grant').addEventListener('click', event => {
                    if (!event.isTrusted) return;
                    window.__grants++;
                    document.getElementById('permission').remove();
                });
            }""")
            session = await context.new_cdp_session(page)
            try:
                target_info = await session.send("Target.getTargetInfo")
            finally:
                await session.detach()
            info = target_info.get("targetInfo")
            assert isinstance(info, dict)
            target_id = info.get("targetId")
            assert isinstance(target_id, str)

            driver = PatchrightDriver(
                profile=tmp_path, debugger_address=address,
                ownership_prefix="prompta-delivery:",
            )
            driver.context = "captured"
            driver._pages["captured"] = page
            driver._owned_target_ids["captured"] = target_id
            driver._send_capture = {}
            marker = new_owned_window_marker(
                prefix="prompta-delivery:", owner_id=driver.page_owner_id,
            )
            await page.evaluate("(value) => { window.name = value; }", marker)
            assert await driver.retry_connector_approval_from_owned_tab() is True
            assert await page.evaluate("window.__grants") == 1

            # A re-used page with a different ownership marker must be inert.
            await page.evaluate("""() => {
                window.name = 'not-a-prompta-owned-tab';
                const permission = document.createElement('div');
                permission.setAttribute('role', 'dialog');
                permission.innerHTML = '<button>Always allow</button><button>Allow once</button>';
                document.body.appendChild(permission);
            }""")
            assert await driver.retry_connector_approval_from_owned_tab() is False
            assert await page.evaluate("window.__grants") == 1
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


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
                '<div role="dialog"><button onclick="document.body.dataset.events=(document.body.dataset.events||\'\')+(event.isTrusted?\'T\':\'F\');'
                'if(event.isTrusted)this.parentElement.remove()">Always allow</button>'
                '<button>Allow once</button><button>Deny</button></div>'
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
                active=lambda: True,
                trusted_retry=lambda: trusted_approval_retry(page),
            )
            assert grants == 1
            assert await page.evaluate("document.body.dataset.approved") == "true"
        finally:
            await browser.close()
