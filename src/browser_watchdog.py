"""Recover Prompta's browser when its CDP HTTP endpoint stops responding."""

from __future__ import annotations

import json
import logging
import os
import sqlite3
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from urllib.request import urlopen

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
    restart = decide_restart(state, healthy=healthy, busy=busy, now=now)
    if restart:
        active = subprocess.run(
            ["systemctl", "--user", "is-active", "--quiet", "prompta-browser.service"],
            check=False,
            timeout=10,
        ).returncode == 0
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
