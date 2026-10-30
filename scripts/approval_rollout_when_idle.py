"""One-shot guarded rollout of live connector approval supervision on Nox.

Used when a deployment lands while delivery captures or manual replies are active.
Do not restart their processes until all leased in-flight work has drained.
"""

from __future__ import annotations

import logging
import sqlite3
import subprocess
import time
from pathlib import Path

logger = logging.getLogger(__name__)
STATE_DIR = Path.home() / ".local/state/prompta"
POLL_SECONDS = 20
MAX_WAIT_SECONDS = 6 * 60 * 60


def active_work(now: float) -> tuple[int, int, bool]:
    responses = STATE_DIR / "chat-results.sqlite3"
    runtime = STATE_DIR / "runtime.sqlite3"
    with sqlite3.connect(f"file:{responses}?mode=ro", uri=True, timeout=3) as db:
        jobs = db.execute(
            "SELECT count(*) FROM job_responses WHERE capture_deadline > ? "
            "AND capture_owner IS NOT NULL AND status IN ('accepted', 'generating', 'partial')",
            (now,),
        ).fetchone()
        replies = db.execute(
            "SELECT count(*) FROM manual_reply_turns WHERE lease_deadline > ? "
            "AND status IN ('dispatching', 'accepted', 'generating', 'partial')",
            (now,),
        ).fetchone()
    with sqlite3.connect(f"file:{runtime}?mode=ro", uri=True, timeout=3) as db:
        rows = db.execute(
            "SELECT activity FROM service_health WHERE service IN ('delivery_worker', 'ui')"
        ).fetchall()
    busy = any(
        isinstance(row[0], str)
        and (row[0].startswith("dispatch:") or row[0].startswith("reply:"))
        for row in rows
    )
    return int(jobs[0]) if jobs else 0, int(replies[0]) if replies else 0, busy


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    deadline = time.monotonic() + MAX_WAIT_SECONDS
    while time.monotonic() < deadline:
        try:
            jobs, replies, busy = active_work(time.time())
            if not jobs and not replies and not busy:
                # Double-check immediately before the restart to minimize races
                # with a newly accepted send or manual reply.
                jobs, replies, busy = active_work(time.time())
                if not jobs and not replies and not busy:
                    for service in ("prompta-delivery-worker.service", "prompta-ui.service"):
                        subprocess.run(["systemctl", "--user", "restart", service], check=True)
                    logger.info("Live approval supervisor deployed after in-flight work drained")
                    return
            logger.info(
                "Deferring live approval rollout active_captures=%d active_replies=%d busy=%s",
                jobs,
                replies,
                busy,
            )
        except (OSError, sqlite3.Error, subprocess.CalledProcessError) as exc:
            logger.warning("Live approval rollout check failed type=%s", type(exc).__name__)
        time.sleep(POLL_SECONDS)
    raise SystemExit("Live approval rollout timed out; services left uninterrupted")


if __name__ == "__main__":
    main()
