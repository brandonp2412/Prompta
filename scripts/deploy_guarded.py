"""Deploy Prompta promptly and recover interrupted captures from browser history.

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

from prompta.deployment_gate import DeploymentGate, deployment_recovery_priority
from prompta.logging_config import configure_logging

logger = logging.getLogger(__name__)
SERVICES = (
    "prompta-scheduler.service",
    "prompta-ui.service",
    "prompta-delivery-worker.service",
    "prompta-manual-reply-worker.service",
)
DEFAULT_STATE = Path.home() / ".local/state/prompta/runtime.sqlite3"


def request_pause(gate: DeploymentGate) -> None:
    descriptor = os.open(gate.pause_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as marker:
        marker.write(f"pid={os.getpid()} time={time.time():.0f}\n")


def stop_workers(*, timeout: float = 60.0) -> None:
    """Stop only after graceful drain; never kill an accepted ChatGPT capture."""
    subprocess.run(["systemctl", "--user", "stop", "--no-block", *SERVICES], check=True)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if all(
            subprocess.run(
                ["systemctl", "--user", "show", "--property=ActiveState", "--value", unit],
                check=True,
                capture_output=True,
                text=True,
                timeout=3,
            ).stdout.strip()
            in {"inactive", "failed"}
            for unit in SERVICES
        ):
            return
        time.sleep(0.25)
    raise TimeoutError("Workers did not drain; deployment must not kill active captures")


_DRAIN_TIMEOUT_SECONDS = 180.0


def wait_for_idle(gate: DeploymentGate, *, timeout: float = _DRAIN_TIMEOUT_SECONDS) -> bool:
    """Drain admitted sends/captures before stopping their owners."""
    state_dir = gate.pause_path.parent
    deadline = time.monotonic() + max(0.0, timeout)
    checks = (
        (
            "chat-results.sqlite3",
            "job_responses",
            "status IN ('accepted', 'generating')",
            "capture_deadline",
        ),
        (
            "chat-results.sqlite3",
            "manual_reply_turns",
            "status IN ('dispatching', 'accepted', 'generating')",
            "lease_deadline",
        ),
        ("ui-send-jobs.sqlite3", "job_deliveries", "status = 'running'", "lease_expires_at"),
    )
    while True:
        now = time.time()
        active = 0
        for filename, table, condition, lease_column in checks:
            with sqlite3.connect(
                f"file:{state_dir / filename}?mode=ro",
                uri=True,
                timeout=3,
            ) as db:
                active += int(
                    db.execute(
                        f"SELECT COUNT(*) FROM {table} WHERE {condition} AND {lease_column}>?",
                        (now,),
                    ).fetchone()[0]
                )
        if active == 0:
            # History probes and parent recovery hold a shared operation lock,
            # but have no capture lease in either database. Do not stop their
            # browser-owning process while one of these read-only probes runs.
            with gate.lock_path.open("a+b") as lock_handle:
                try:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
                    return True
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            logger.warning("Deployment deferred: %s active leases or browser reads remain", active)
            return False
        time.sleep(min(3.0, remaining))


def record_interrupted_work(gate: DeploymentGate) -> None:
    """Keep a durable deployment inventory before stopping any owners."""
    state_dir = gate.pause_path.parent
    inventory: dict[str, object] = {"recorded_at": time.time()}
    previous = deployment_recovery_priority(state_dir)
    priority: dict[str, list[str]] = {
        "job_responses": list(previous[0]),
        "manual_reply_turns": list(previous[1]),
    }
    for filename, table, key in (
        ("chat-results.sqlite3", "job_responses", "send_id"),
        ("chat-results.sqlite3", "manual_reply_turns", "reply_id"),
        ("ui-send-jobs.sqlite3", "job_deliveries", "send_id"),
    ):
        with sqlite3.connect(f"file:{state_dir / filename}?mode=ro", uri=True, timeout=3) as db:
            rows = db.execute(
                f"SELECT {key}, status FROM {table} WHERE status IN "
                "('running', 'dispatching', 'accepted', 'generating', 'partial', "
                "'interrupted', 'outcome_unknown')"
            ).fetchall()
        inventory[table] = [{"id": row[0], "status": row[1]} for row in rows]
        if table in priority:
            # Only captures owned at deploy time get fast-lane recovery. Older
            # interrupted/outcome-unknown rows stay in the ordinary paced queue.
            in_flight = {"accepted", "generating", "partial", "dispatching"}
            recent = [str(identifier) for identifier, status in rows if status in in_flight]
            priority[table] = list(dict.fromkeys(recent + priority[table]))[:512]
    inventory["priority"] = priority
    target = state_dir / "deployment-interrupted.json"
    temporary = target.with_suffix(".tmp")
    temporary.write_text(json.dumps(inventory, indent=2) + "\n", encoding="utf-8")
    temporary.replace(target)
    logger.info("Recorded interrupted work in %s", target)


def verify_recorded_work(gate: DeploymentGate) -> bool:
    """Confirm deploy-time operation IDs survived the restart.

    Pending recovery is explicitly reported, never presented as completed.
    Recovery itself resumes only after the admission pause is released.
    """
    state_dir = gate.pause_path.parent
    inventory = json.loads((state_dir / "deployment-interrupted.json").read_text(encoding="utf-8"))
    observations: dict[str, dict[str, int]] = {}
    missing: dict[str, list[str]] = {}
    pending = 0
    preserved = 0
    for filename, table, key in (
        ("chat-results.sqlite3", "job_responses", "send_id"),
        ("chat-results.sqlite3", "manual_reply_turns", "reply_id"),
        ("ui-send-jobs.sqlite3", "job_deliveries", "send_id"),
    ):
        items = inventory.get(table)
        if not isinstance(items, list):
            raise ValueError(f"Invalid deployment recovery inventory table={table}")
        counts: dict[str, int] = {}
        lost: list[str] = []
        with sqlite3.connect(f"file:{state_dir / filename}?mode=ro", uri=True, timeout=3) as db:
            for item in items:
                if not isinstance(item, dict) or not isinstance(item.get("id"), str):
                    raise ValueError(f"Invalid deployment recovery inventory record table={table}")
                identifier = item["id"]
                row = db.execute(
                    f"SELECT status FROM {table} WHERE {key}=?", (identifier,)
                ).fetchone()
                if row is None:
                    lost.append(identifier)
                    continue
                preserved += 1
                status = str(row[0])
                counts[status] = counts.get(status, 0) + 1
                if status in {
                    "running",
                    "dispatching",
                    "accepted",
                    "generating",
                    "partial",
                    "interrupted",
                    "outcome_unknown",
                }:
                    pending += 1
        observations[table] = counts
        if lost:
            missing[table] = lost

    report = {
        "recorded_at": inventory.get("recorded_at"),
        "checked_at": time.time(),
        "preserved": preserved,
        "pending_recovery": pending,
        "missing": missing,
        "status_counts": observations,
    }
    destination = state_dir / "deployment-verification.json"
    temporary = destination.with_suffix(".tmp")
    temporary.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    temporary.replace(destination)
    level = logging.ERROR if missing else logging.INFO
    logger.log(
        level,
        "event=deployment_continuity_checked preserved=%d pending_recovery=%d missing=%d report=%s",
        preserved,
        pending,
        sum(len(ids) for ids in missing.values()),
        destination,
    )
    return not missing


def verify_services(*, timeout: float = 45.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        units_active = all(
            subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet", unit],
                check=False,
            ).returncode
            == 0
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


def deploy(repo: Path, gate: DeploymentGate) -> bool:
    """Stop owners before updating; startup recovery reconciles durable captures."""
    merge_lock = repo / ".git/prompta-main-merge.lock"
    with merge_lock.open("a+b") as merge_handle:
        fcntl.flock(merge_handle.fileno(), fcntl.LOCK_EX)
        # Fetch is safe before pausing browser operations; checkout is not.
        subprocess.run(["git", "fetch", "origin", "main"], cwd=repo, check=True)
        if subprocess.run(["git", "diff", "--quiet"], cwd=repo, check=False).returncode != 0:
            raise RuntimeError("Installed checkout has local modifications")
        request_pause(gate)
        changed = False
        success = False
        try:
            if not wait_for_idle(gate):
                return False
            record_interrupted_work(gate)
            changed = True
            stop_workers()
            # Every browser-owning process is stopped. Expire all of its
            # capture leases so the new workers mark them interrupted on boot,
            # even if an old PID is unexpectedly reused. Nothing is resent.
            with sqlite3.connect(gate.pause_path.parent / "chat-results.sqlite3") as db:
                db.execute(
                    "UPDATE job_responses SET capture_deadline=0 "
                    "WHERE status IN ('accepted', 'generating')"
                )
                db.execute(
                    "UPDATE manual_reply_turns SET lease_deadline=0 "
                    "WHERE status IN ('dispatching', 'accepted', 'generating')"
                )
            # Unconfirmed deliveries are also quarantined without retry.
            with sqlite3.connect(gate.pause_path.parent / "ui-send-jobs.sqlite3") as db:
                db.execute("UPDATE job_deliveries SET lease_expires_at=0 WHERE status='running'")
            subprocess.run(["git", "merge", "--ff-only", "origin/main"], cwd=repo, check=True)
            subprocess.run([str(repo / ".venv/bin/prompta-migrate")], cwd=repo, check=True)
            # The browser process, its tabs and profile are never restarted here.
            for unit in SERVICES:
                subprocess.run(["systemctl", "--user", "restart", unit], check=True)
            if not verify_services():
                raise RuntimeError("Deployment health verification failed; admission stays paused")
            if not verify_recorded_work(gate):
                raise RuntimeError("Deployment lost recorded work; admission stays paused")
            logger.info("event=deployment_health_verified recovery_may_be_pending=true")
            success = True
            return True
        finally:
            if not changed or success:
                gate.pause_path.unlink()
            else:
                logger.error("Deployment incomplete; pause marker retained until operator recovery")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.home() / "prompta")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Remove a leftover pause only after separately verifying services are healthy",
    )
    args = parser.parse_args()
    configure_logging("deploy_guarded")
    gate = DeploymentGate(args.state)
    if args.resume:
        if not verify_services():
            raise SystemExit("Services are not healthy; refusing to resume")
        gate.pause_path.unlink(missing_ok=True)
        return
    if not deploy(args.repo.resolve(), gate):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
