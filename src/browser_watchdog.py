"""Recover Prompta's browser when its CDP HTTP endpoint stops responding."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

from playwright.async_api import async_playwright

from .browser_ownership import (
    MAX_OWNED_TAB_AGE_SECONDS,
    forget_owned_tabs,
    owned_tab_records,
    owned_window_owner_id,
    owned_window_started_at,
)
from .browser_script_loader import load_browser_script

logger = logging.getLogger(__name__)
STATE_DIR = Path.home() / ".local/state/prompta"
STATE_FILE = STATE_DIR / "browser-watchdog.json"
FAILURE_THRESHOLD = 2
RESTART_COOLDOWN_SECONDS = 300.0


@dataclass
class WatchdogState:
    consecutive_failures: int = 0
    last_restart_at: float = 0.0


def debugger_responding(address: str = "127.0.0.1:9222") -> bool:
    try:
        with urlopen(f"http://{address}/json/version", timeout=3.0) as response:
            payload = json.load(response)
        return isinstance(payload, dict) and bool(payload.get("webSocketDebuggerUrl"))
    except (OSError, ValueError):
        return False


def delivery_in_flight(database: Path, now: float) -> bool:
    """Avoid killing Brave during a recently started send with an unknown outcome."""
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=1.0) as connection:
            row = connection.execute(
                "SELECT activity, activity_started_at FROM service_health WHERE service = ?",
                ("delivery_worker",),
            ).fetchone()
    except sqlite3.Error:
        logger.warning("Cannot inspect in-flight delivery; deferring browser restart")
        return True
    if row is None:
        return False
    activity, started_at = row
    return (
        isinstance(activity, str)
        and activity.startswith("dispatch:")
        and 0 <= now - float(started_at) < 300.0
    )


def reap_expired_leases_http(
    address: str = "127.0.0.1:9222",
    *,
    now: float | None = None,
) -> int:
    """Browser HTTP fallback when Playwright/CDP websocket supervision fails."""
    current = time.time() if now is None else now
    with urlopen(f"http://{address}/json/list", timeout=3.0) as response:
        targets = json.load(response)
    if not isinstance(targets, list):
        raise ValueError("CDP target listing is not a list")
    active = {
        target.get("id")
        for target in targets
        if isinstance(target, dict)
        and target.get("type") == "page"
        and isinstance(target.get("id"), str)
    }
    leases = owned_tab_records()
    resolved = set(leases) - active
    closed = 0
    for target_id, opened_at in leases.items():
        if target_id not in active or opened_at > current - MAX_OWNED_TAB_AGE_SECONDS:
            continue
        try:
            with urlopen(f"http://{address}/json/close/{quote(target_id, safe='')}", timeout=3.0):
                pass
            resolved.add(target_id)
            closed += 1
        except OSError as exc:
            logger.warning("Prompta HTTP expiry failed error_type=%s", type(exc).__name__)
    forget_owned_tabs(resolved)
    return closed


async def reap_expired_owned_tabs(
    address: str = "127.0.0.1:9222",
    *,
    now: float | None = None,
) -> int:
    """Close only Prompta-owned expired targets; never navigate or reload pages."""
    current = time.time() if now is None else now
    expired_before = current - MAX_OWNED_TAB_AGE_SECONDS
    closed = 0
    async with async_playwright() as playwright:
        browser = await playwright.chromium.connect_over_cdp(
            f"http://{address}",
            timeout=5000,
        )
        session = await browser.new_browser_cdp_session()
        try:
            targets = (await session.send("Target.getTargets")).get("targetInfos", [])
            active = {
                target.get("targetId")
                for target in targets
                if isinstance(target, dict)
                and target.get("type") == "page"
                and isinstance(target.get("targetId"), str)
            }
            try:
                leases = owned_tab_records()
            except sqlite3.Error as exc:
                logger.warning(
                    "Prompta tab lease database unreadable error_type=%s", type(exc).__name__
                )
                leases = {}
            resolved = set(leases) - active
            for target_id, opened_at in leases.items():
                if target_id not in active or opened_at > expired_before:
                    continue
                try:
                    result = await asyncio.wait_for(
                        session.send("Target.closeTarget", {"targetId": target_id}),
                        timeout=3.0,
                    )
                    if result.get("success") is True:
                        resolved.add(target_id)
                        closed += 1
                except Exception as exc:
                    logger.warning("Prompta tab expiry failed error_type=%s", type(exc).__name__)

            # Discover tabs created before the lease ledger, or when registering failed.
            for context in browser.contexts:
                for page in context.pages:
                    if page.is_closed():
                        continue
                    try:
                        marker = await asyncio.wait_for(page.evaluate(load_browser_script("get_window_name.js")), timeout=0.5)
                        started_at = owned_window_started_at(marker)
                        owner_id = owned_window_owner_id(marker)
                        if started_at is None or owner_id is None or started_at > expired_before:
                            continue
                        page_session = await page.context.new_cdp_session(page)
                        try:
                            info = await page_session.send("Target.getTargetInfo")
                        finally:
                            await page_session.detach()
                        target_info = info.get("targetInfo")
                        target_id = (
                            target_info.get("targetId") if isinstance(target_info, dict) else None
                        )
                        if not isinstance(target_id, str) or target_id in resolved:
                            continue
                        result = await asyncio.wait_for(
                            session.send("Target.closeTarget", {"targetId": target_id}),
                            timeout=3.0,
                        )
                        if result.get("success") is True:
                            resolved.add(target_id)
                            closed += 1
                    except Exception as exc:
                        logger.warning(
                            "Prompta marker expiry check failed error_type=%s", type(exc).__name__
                        )
            forget_owned_tabs(resolved)
        finally:
            # Stopping Playwright disconnects without closing the shared Brave browser.
            await session.detach()
    if closed:
        logger.warning("Reaped %d expired Prompta-owned tabs", closed)
    return closed


def load_state(path: Path) -> WatchdogState:
    try:
        data = json.loads(path.read_text())
        if isinstance(data, dict):
            return WatchdogState(
                consecutive_failures=max(0, int(data.get("consecutive_failures", 0))),
                last_restart_at=max(0.0, float(data.get("last_restart_at", 0))),
            )
    except (OSError, ValueError, TypeError):
        pass
    return WatchdogState()


def save_state(path: Path, state: WatchdogState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    temporary.write_text(
        json.dumps(
            {
                "consecutive_failures": state.consecutive_failures,
                "last_restart_at": state.last_restart_at,
            }
        )
        + "\n"
    )
    os.replace(temporary, path)


def decide_restart(
    state: WatchdogState,
    *,
    healthy: bool,
    busy: bool,
    now: float,
) -> bool:
    if healthy:
        state.consecutive_failures = 0
        return False
    state.consecutive_failures += 1
    return (
        state.consecutive_failures >= FAILURE_THRESHOLD
        and now - state.last_restart_at >= RESTART_COOLDOWN_SECONDS
        and not busy
    )


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    now = time.time()
    state = load_state(STATE_FILE)
    healthy = debugger_responding()
    busy = False if healthy else delivery_in_flight(STATE_DIR / "runtime.sqlite3", now)
    if healthy:
        try:
            asyncio.run(reap_expired_owned_tabs(now=now))
        except Exception as exc:
            logger.warning(
                "Prompta independent tab reaper failed error_type=%s", type(exc).__name__
            )
            try:
                reap_expired_leases_http(now=now)
            except Exception as fallback_exc:
                logger.error(
                    "Prompta HTTP tab reaper failed error_type=%s", type(fallback_exc).__name__
                )
    restart = decide_restart(state, healthy=healthy, busy=busy, now=now)
    if restart:
        active = (
            subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet", "prompta-browser.service"],
                check=False,
                timeout=10,
            ).returncode
            == 0
        )
        if not active:
            logger.info("Brave service is intentionally inactive; not restarting it")
            state.consecutive_failures = 0
            save_state(STATE_FILE, state)
            return
        logger.warning("Brave CDP unavailable on consecutive checks; restarting browser service")
        subprocess.run(
            ["systemctl", "--user", "restart", "prompta-browser.service"],
            check=True,
            timeout=60,
        )
        state.consecutive_failures = 0
        state.last_restart_at = time.time()
        logger.info("Brave restarted; next watchdog check will verify debugger health")
    elif not healthy:
        logger.warning(
            "Brave CDP unhealthy failures=%d delivery_in_flight=%s",
            state.consecutive_failures,
            busy,
        )
    save_state(STATE_FILE, state)


if __name__ == "__main__":
    main()
