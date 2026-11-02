"""Deploy a new worker generation while live chats retain their original workers.

Run from the installed Prompta checkout: python scripts/deploy_guarded.py
Queued submissions stay durable. The browser service is deliberately untouched.
"""

from __future__ import annotations

import argparse
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
HANDOFF_WAIT_SECONDS = 180.0


def request_pause(gate: DeploymentGate) -> None:
    descriptor = os.open(gate.pause_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as marker:
        marker.write(f"pid={os.getpid()} time={time.time():.0f}\n")


def wait_for_recoverable_handoff(
    gate: DeploymentGate, *, timeout: float = HANDOFF_WAIT_SECONDS,
) -> None:
    """Do not kill a dispatch whose accepted conversation cannot yet be recovered.

    The deployment pause prevents new admissions. Existing generations can
    continue for hours, but a bounded wait for their *send handoff* protects
    against permanently ambiguous sends and identity-less interrupted reads.
    """
    state_dir = gate.pause_path.parent
    deadline = time.monotonic() + max(0.0, timeout)
    while True:
        with sqlite3.connect(
            f"file:{state_dir / 'ui-send-jobs.sqlite3'}?mode=ro", uri=True, timeout=3
        ) as db:
            running = db.execute(
                "SELECT COUNT(*) FROM job_deliveries WHERE status='running'"
            ).fetchone()[0]
        with sqlite3.connect(
            f"file:{state_dir / 'chat-results.sqlite3'}?mode=ro", uri=True, timeout=3
        ) as db:
            unidentified = db.execute(
                "SELECT COUNT(*) FROM job_responses "
                "WHERE status IN ('accepted', 'generating') "
                "AND COALESCE(conversation_id, '')=''"
            ).fetchone()[0]
            replies = db.execute(
                "SELECT COUNT(*) FROM manual_reply_turns "
                "WHERE status='dispatching' OR "
                "(status IN ('accepted', 'generating') AND "
                "(COALESCE(conversation_id, '')='' OR COALESCE(parent_id, '')=''))"
            ).fetchone()[0]
        if not (running or unidentified or replies):
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                "Deployment deferred: unverified handoffs remain "
                f"(running_deliveries={running}, unidentified_captures={unidentified}, "
                f"unverified_replies={replies}); workers and browser were not stopped"
            )
        time.sleep(min(1.0, remaining))


def stop_workers(*, timeout: float = 60.0) -> None:
    """Emergency browser-crash recovery only; routine deployment never calls this."""
    from scripts.rolling_deploy import FRONTENDS, all_worker_units

    services = (*FRONTENDS, *all_worker_units())
    subprocess.run(["systemctl", "--user", "stop", "--no-block", *services], check=True)
    # Queue stop first so Restart=always cannot relaunch a killed owner.
    # A unit may already be inactive; the state check below confirms shutdown.
    subprocess.run(
        ["systemctl", "--user", "kill", "--signal=SIGKILL", "--kill-whom=all", *services],
        check=False,
    )
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
            for unit in services
        ):
            return
        time.sleep(0.25)
    raise TimeoutError("Application workers did not stop; refusing to update their loaded checkout")


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


def verify_services(
    *, timeout: float = 45.0, units: tuple[str, ...] | None = None, check_http: bool = True,
    ready_dir: Path | None = None,
) -> bool:
    if units is None:
        from scripts.rolling_deploy import FRONTENDS, current_workers

        units = (*FRONTENDS, *current_workers(DEFAULT_STATE.parent))
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        units_active = all(
            subprocess.run(
                ["systemctl", "--user", "is-active", "--quiet", unit],
                check=False,
            ).returncode
            == 0
            for unit in units
        )
        if units_active and ready_dir is not None:
            for unit in units:
                ready = ready_dir / ("ready-" + unit.split("-worker-", 1)[0])
                pid = subprocess.run(
                    ["systemctl", "--user", "show", "-p", "MainPID", "--value", unit],
                    check=True, capture_output=True, text=True,
                ).stdout.strip()
                if not ready.exists() or ready.read_text().strip() != pid or pid == "0":
                    units_active = False
                    break
        if units_active:
            if not check_http:
                return True
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
    """Start an immutable generation while previous owners drain in place."""
    from scripts.rolling_deploy import deploy as rolling_deploy

    return rolling_deploy(repo, gate)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=Path.home() / "prompta")
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Remove a leftover pause only after separately verifying services are healthy",
    )
    parser.add_argument("--sync-checkout", action="store_true")
    args = parser.parse_args()
    configure_logging("deploy_guarded")
    if args.sync_checkout:
        from scripts.rolling_deploy import sync_checkout

        with (args.repo / ".git/prompta-main-merge.lock").open("a+b") as lock:
            import fcntl

            fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            if sync_checkout(args.repo):
                subprocess.run(["systemctl", "--user", "disable", "--now",
                                "prompta-checkout-sync.timer"], check=True)
        return
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
