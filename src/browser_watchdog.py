"""Recover Prompta's configured browser when its CDP endpoint stops responding."""

from __future__ import annotations

import asyncio
import fcntl
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

from patchright.async_api import async_playwright as async_patchright

from .browser_ownership import (
    MAX_OWNED_TAB_AGE_SECONDS,
    claim_expired_tab,
    forget_owned_tabs,
    owned_tab_records,
)
from .deployment_gate import DeploymentGate
from .reply_contracts import ManualReplyStore

logger = logging.getLogger(__name__)
STATE_DIR = Path.home() / ".local/state/prompta"
STATE_FILE = STATE_DIR / "browser-watchdog.json"
FAILURE_THRESHOLD = 2
RESTART_COOLDOWN_SECONDS = 300.0
MAX_EXPIRED_TABS_PER_TICK = 4


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


async def renderer_responding(address: str) -> bool:
    """Exercise a new renderer without navigating to ChatGPT or sending a prompt."""
    try:
        async with async_patchright() as patchright:
            browser = await patchright.chromium.connect_over_cdp(
                f"http://{address}", timeout=5000,
            )
            page = await browser.contexts[0].new_page()
            try:
                result: object = await page.evaluate("1 + 1")
                return isinstance(result, int) and result == 2
            finally:
                await page.close()
    except Exception as exc:
        logger.warning("Browser renderer probe failed error_type=%s", type(exc).__name__)
        return False


async def bounded_renderer_probe(address: str) -> bool:
    try:
        return await asyncio.wait_for(renderer_responding(address), timeout=10.0)
    except TimeoutError:
        logger.warning("Browser renderer probe timed out")
        return False


def delivery_in_flight(database: Path, now: float) -> bool:
    """Fail closed if a browser restart could interrupt a durable send or capture.

    The worker's health row describes only its latest activity. Parallel
    dispatches can overwrite one another there, so check each persisted lease.
    """
    try:
        with sqlite3.connect(f"file:{database}?mode=ro", uri=True, timeout=1.0) as connection:
            row = connection.execute(
                "SELECT activity, activity_started_at FROM service_health WHERE service = ?",
                ("delivery_worker",),
            ).fetchone()
    except (OSError, sqlite3.Error):
        logger.warning("Cannot inspect in-flight delivery; deferring browser restart")
        return True
    if row is not None:
        activity, started_at = row
        if isinstance(activity, str) and activity.startswith("dispatch:"):
            try:
                if 0 <= now - float(started_at) < 300.0:
                    return True
            except (TypeError, ValueError):
                logger.warning("Invalid delivery activity timestamp; deferring browser restart")
                return True

    def active_lease(path: Path, query: str) -> bool:
        try:
            if not path.exists():
                return False
            with sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1.0) as connection:
                return connection.execute(query, (now,)).fetchone() is not None
        except (OSError, sqlite3.Error):
            logger.warning("Cannot inspect %s leases; deferring browser restart", path.name)
            return True

    state_dir = database.parent
    return (
        active_lease(
            state_dir / "ui-send-jobs.sqlite3",
            "SELECT 1 FROM job_deliveries "
            "WHERE status = 'running' AND lease_owner != '' "
            "AND lease_expires_at > ? LIMIT 1",
        )
        or active_lease(
            state_dir / "chat-results.sqlite3",
            "SELECT 1 FROM manual_reply_turns "
            "WHERE status IN ('dispatching', 'accepted', 'generating') "
            "AND lease_owner != '' AND lease_deadline > ? LIMIT 1",
        )
        or active_lease(
            state_dir / "chat-results.sqlite3",
            "SELECT 1 FROM job_responses "
            "WHERE status IN ('accepted', 'generating') "
            "AND capture_owner != '' AND capture_deadline > ? LIMIT 1",
        )
    )


def reap_expired_leases_http(
    address: str = "127.0.0.1:9222",
    *,
    now: float | None = None,
) -> int:
    """Bounded HTTP cleanup when the CDP websocket cannot be used."""
    current = time.time() if now is None else now
    cutoff = current - MAX_OWNED_TAB_AGE_SECONDS
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
    forget_owned_tabs(set(leases) - active)
    closed = 0
    attempts = 0
    for target_id, last_activity in leases.items():
        if attempts >= MAX_EXPIRED_TABS_PER_TICK:
            break
        if target_id not in active or last_activity > cutoff:
            continue
        attempts += 1
        try:
            with claim_expired_tab(target_id, cutoff) as mark_closed:
                if mark_closed is None:
                    continue
                with urlopen(
                    f"http://{address}/json/close/{quote(target_id, safe='')}",
                    timeout=3.0,
                ):
                    pass
                mark_closed()
                closed += 1
        except (OSError, sqlite3.Error) as exc:
            logger.warning("Prompta HTTP expiry failed error_type=%s", type(exc).__name__)
    return closed


async def reap_expired_owned_tabs(
    address: str = "127.0.0.1:9222",
    *,
    now: float | None = None,
) -> int:
    """Close only ledger-verified expired targets without inspecting other tabs."""
    current = time.time() if now is None else now
    cutoff = current - MAX_OWNED_TAB_AGE_SECONDS
    closed = 0
    async with async_patchright() as patchright:
        browser = await asyncio.wait_for(
            patchright.chromium.connect_over_cdp(f"http://{address}", timeout=5000),
            timeout=6.0,
        )
        session = await asyncio.wait_for(browser.new_browser_cdp_session(), timeout=3.0)
        try:
            targets = (await asyncio.wait_for(
                session.send("Target.getTargets"), timeout=3.0,
            )).get("targetInfos", [])
            active = {
                target.get("targetId")
                for target in targets
                if isinstance(target, dict)
                and target.get("type") == "page"
                and isinstance(target.get("targetId"), str)
            }
            leases = owned_tab_records()
            forget_owned_tabs(set(leases) - active)
            attempts = 0
            for target_id, last_activity in leases.items():
                if attempts >= MAX_EXPIRED_TABS_PER_TICK:
                    break
                if target_id not in active or last_activity > cutoff:
                    continue
                attempts += 1
                try:
                    with claim_expired_tab(target_id, cutoff) as mark_closed:
                        if mark_closed is None:
                            continue
                        result = await asyncio.wait_for(
                            session.send("Target.closeTarget", {"targetId": target_id}),
                            timeout=3.0,
                        )
                        if result.get("success") is True:
                            mark_closed()
                            closed += 1
                except Exception as exc:
                    logger.warning("Prompta tab expiry failed error_type=%s", type(exc).__name__)
        finally:
            try:
                await asyncio.wait_for(session.detach(), timeout=2.0)
            except Exception as exc:
                logger.debug("Prompta watchdog detach failed error_type=%s", type(exc).__name__)
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
    gate = DeploymentGate(STATE_DIR / "runtime.sqlite3")
    # Serialize probes and restarts against every worker browser operation.
    with gate.lock_path.open("a+b") as handle:
        try:
            fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return
        try:
            if not gate.is_paused():
                check_browser()
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def check_browser() -> None:
    now = time.time()
    state = load_state(STATE_FILE)
    address = os.environ.get("PROMPTA_CHROME_DEBUGGER_ADDRESS", "127.0.0.1:9222")
    browser_service = os.environ.get("PROMPTA_BROWSER_SERVICE", "prompta-browser.service")
    try:
        ManualReplyStore(STATE_DIR / "chat-results.sqlite3").recover_orphans(now=now)
    except Exception as exc:
        logger.warning("Manual reply lease recovery failed error_type=%s", type(exc).__name__)
    healthy = debugger_responding(address)
    busy = delivery_in_flight(STATE_DIR / "runtime.sqlite3", now)
    if healthy and not busy:
        healthy = asyncio.run(bounded_renderer_probe(address))
    if healthy and not busy:
        try:
            asyncio.run(reap_expired_owned_tabs(address=address, now=now))
        except Exception as exc:
            logger.warning(
                "Prompta independent tab reaper failed error_type=%s", type(exc).__name__
            )
            try:
                reap_expired_leases_http(address=address, now=now)
            except Exception as fallback_exc:
                logger.error(
                    "Prompta HTTP tab reaper failed error_type=%s", type(fallback_exc).__name__
                )
    restart = decide_restart(state, healthy=healthy, busy=busy, now=now)
    if restart:
        active = (
            subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet", browser_service],
                check=False,
                timeout=10,
            ).returncode
            == 0
        )
        if not active:
            logger.info("Browser service %s is intentionally inactive; not restarting it", browser_service)
            state.consecutive_failures = 0
            save_state(STATE_FILE, state)
            return
        logger.warning("Browser endpoint or renderer unavailable; restarting %s", browser_service)
        subprocess.run(
            ["systemctl", "--user", "restart", browser_service],
            check=True,
            timeout=60,
        )
        state.consecutive_failures = 0
        state.last_restart_at = time.time()
        logger.info("Browser restarted; next watchdog check will verify debugger health")
    elif not healthy:
        logger.warning(
            "Browser CDP unhealthy failures=%d delivery_in_flight=%s",
            state.consecutive_failures,
            busy,
        )
    save_state(STATE_FILE, state)


if __name__ == "__main__":
    main()
