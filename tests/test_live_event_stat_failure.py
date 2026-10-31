"""Transient local filesystem failure must not strand active SSE clients."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from prompta.live_events import LocalEventSignals


def test_live_revisions_preserve_last_known_state_during_stat_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    jobs = tmp_path / "jobs.sqlite3"
    state = tmp_path / "runtime.sqlite3"
    with sqlite3.connect(state) as db:
        db.execute(
            "CREATE TABLE scheduler_state (scope TEXT, name TEXT, key TEXT, value_json TEXT)"
        )
        db.execute("CREATE TABLE account_state (key TEXT, value_json TEXT)")
        db.execute(
            "INSERT INTO scheduler_state VALUES (?, ?, ?, ?)",
            ("scheduler", "jobs", "revision", "1"),
        )

    signals = LocalEventSignals(jobs, state)
    baseline = signals.snapshot()
    assert baseline.jobs[2] != (0, 0, 0)
    stat = Path.stat

    def intermittent(path: Path, *, follow_symlinks: bool = True):
        if path == state:
            raise PermissionError("Transient metadata failure")
        return stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", intermittent)
    assert signals.snapshot().jobs == baseline.jobs

    monkeypatch.setattr(Path, "stat", stat)
    with sqlite3.connect(state) as db:
        db.execute(
            "UPDATE scheduler_state SET value_json = ? WHERE key = ?",
            ("2", "revision"),
        )
    recovered = signals.snapshot()
    assert recovered.jobs != baseline.jobs
    assert recovered.jobs[2] != (0, 0, 0)
