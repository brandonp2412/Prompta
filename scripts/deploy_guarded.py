"""Deploy Prompta without interrupting owned browser captures or replies.

Run from the installed Prompta checkout: python scripts/deploy_guarded.py
Queued submissions stay durable. The browser service is deliberately untouched.
"""

from __future__ import annotations

import argparse
import fcntl
import json
import logging
import os
import sqlite3
import subprocess
import time
from pathlib import Path
from urllib.error import URLError
from urllib.request import urlopen

from prompta.deployment_gate import DeploymentGate

logger = logging.getLogger(__name__)
SERVICES = (
    "prompta-scheduler.service",
    "prompta-ui.service",
    "prompta-delivery-worker.service",
    "prompta-manual-reply-worker.service",
)
DEFAULT_STATE = Path.home() / ".local/state/prompta/runtime.sqlite3"


def active_work(state_dir: Path, now: float) -> tuple[int, int, int, bool]:
    """Fail closed on missing/corrupt databases, never guess that work is idle."""
    results = state_dir / "chat-results.sqlite3"
    runtime = state_dir / "runtime.sqlite3"
    deliveries = state_dir / "ui-send-jobs.sqlite3"
    with sqlite3.connect(f"file:{results}?mode=ro", uri=True, timeout=3) as db:
        captures = db.execute(
            "SELECT count(*) FROM job_responses WHERE capture_deadline > ? "
            "AND capture_owner IS NOT NULL "
            "AND status IN ('accepted', 'generating', 'partial')",
            (now,),
        ).fetchone()
        replies = db.execute(
            "SELECT count(*) FROM manual_reply_turns WHERE lease_deadline > ? "
            "AND status IN ('dispatching', 'accepted', 'generating', 'partial')",
            (now,),
        ).fetchone()
    with sqlite3.connect(f"file:{deliveries}?mode=ro", uri=True, timeout=3) as db:
        sends = db.execute(
            "SELECT count(*) FROM job_deliveries WHERE status = 'running' "
            "AND lease_owner != '' AND lease_expires_at > ?",
            (now,),
        ).fetchone()
    with sqlite3.connect(f"file:{runtime}?mode=ro", uri=True, timeout=3) as db:
        rows = db.execute(
            "SELECT activity FROM service_health "
            "WHERE service IN ('delivery_worker', 'ui', 'manual_reply_worker')"
        ).fetchall()
    busy = any(
        isinstance(row[0], str)
        and (row[0].startswith("dispatch:") or row[0].startswith("reply:"))
        for row in rows
    )
    return (
        int(captures[0]) if captures else 0,
        int(replies[0]) if replies else 0,
        int(sends[0]) if sends else 0,
        busy,
    )


def request_pause(gate: DeploymentGate) -> None:
    descriptor = os.open(gate.pause_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as marker:
        marker.write(f"pid={os.getpid()} time={time.time():.0f}\n")


def wait_until_idle(gate: DeploymentGate, *, timeout: float, poll: float = 2.0) -> bool:
    """Wait until admitted operations and persistent leases are both drained."""
    deadline = time.monotonic() + timeout
    with gate.lock_path.open("a+b") as lock:
        while time.monotonic() < deadline:
            try:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                logger.info("Waiting for currently admitted browser operations")
            else:
                try:
                    captures, replies, sends, busy = active_work(
                        gate.pause_path.parent, time.time()
                    )
                    if not (captures or replies or sends or busy):
                        return True
                    logger.info(
                        "Deployment draining captures=%d replies=%d sends=%d busy=%s",
                        captures, replies, sends, busy,
                    )
                except (OSError, sqlite3.Error) as exc:
                    logger.warning(
                        "Unable to verify idle state error_type=%s", type(exc).__name__
                    )
                finally:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)
            time.sleep(min(poll, max(0.0, deadline - time.monotonic())))
    return False


def verify_services(*, timeout: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        units_active = all(
            subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet", unit],
                check=False,
            ).returncode == 0
            for unit in SERVICES
        )
        if units_active:
            try:
                with urlopen("http://127.0.0.1:8765/api/health", timeout=3) as response:
                    payload = json.load(response)
                if payload.get("ok") is True:
                    return True
            except (OSError, URLError, ValueError):
                pass
        time.sleep(2.0)
    return False


def deploy(repo: Path, gate: DeploymentGate, *, wait_seconds: float) -> bool:
    """A failed pre-deployment drain resumes old workers; post-update errors stay paused."""
    merge_lock = repo / ".git/prompta-main-merge.lock"
    with merge_lock.open("a+b") as merge_handle:
        fcntl.flock(merge_handle.fileno(), fcntl.LOCK_EX)
        # Fetch is safe before pausing browser operations; checkout is not.
        subprocess.run(["git", "fetch", "origin", "main"], cwd=repo, check=True)
        if subprocess.run(
            ["git", "diff", "--quiet"], cwd=repo, check=False
        ).returncode != 0:
            raise RuntimeError("Installed checkout has local modifications")
        request_pause(gate)
        changed = False
        success = False
        try:
            if not wait_until_idle(gate, timeout=wait_seconds):
                logger.warning("Deployment deferred; current work was not interrupted")
                return False
            changed = True
            subprocess.run(["git", "merge", "--ff-only", "origin/main"], cwd=repo, check=True)
            subprocess.run([str(repo / ".venv/bin/prompta-migrate")], cwd=repo, check=True)
            # The browser process, its tabs and profile are never restarted here.
            for unit in SERVICES:
                subprocess.run(["systemctl", "--user", "restart", unit], check=True)
            if not verify_services():
                raise RuntimeError("Deployment health verification failed; admission stays paused")
            logger.info("Guarded deployment verified; resuming durable queues")
            success = True
            return True
        finally:
            if not changed or success:
                gate.pause_path.unlink()
            else:
                logger.error(
                    "Deployment incomplete; pause marker retained until operator recovery"
                )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.home() / "prompta")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--wait-minutes", type=float, default=60.0)
    parser.add_argument(
        "--resume", action="store_true",
        help="Remove a leftover pause only after separately verifying services are healthy",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    gate = DeploymentGate(args.state)
    if args.resume:
        if not verify_services():
            raise SystemExit("Services are not healthy; refusing to resume")
        gate.pause_path.unlink(missing_ok=True)
        return
    if args.wait_minutes <= 0:
        parser.error("--wait-minutes must be positive")
    if not deploy(args.repo.resolve(), gate, wait_seconds=args.wait_minutes * 60.0):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
