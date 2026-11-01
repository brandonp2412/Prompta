"""Read-only lease inspection for retired connector approval rollout.

Use scripts.deploy_guarded for any application deployment.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

STATE_DIR = Path.home() / ".local/state/prompta"


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
    raise SystemExit(
        "Legacy approval rollout disabled; use .venv/bin/python -m scripts.deploy_guarded"
    )


if __name__ == "__main__":
    main()
