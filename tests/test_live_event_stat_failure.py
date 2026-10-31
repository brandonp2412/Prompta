"""A transient local metadata failure must preserve revision continuity."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from prompta.live_events import LocalEventSignals
from prompta.persistence import account_state, create_database


def test_live_revisions_preserve_last_known_state_during_stat_failure(
    tmp_path: Path,
    monkeypatch,
) -> None:
    jobs = tmp_path / "jobs.sqlite3"
    state = tmp_path / "runtime.sqlite3"
    engine = create_database(state)
    with engine.begin() as connection:
        connection.execute(account_state.insert().values(key="test", value_json='"before"'))

    signals = LocalEventSignals(jobs, state)
    baseline = signals.snapshot()
    assert baseline.jobs[2] != (0, 0, 0)
    stat = Path.stat

    def intermittent(path: Path, *, follow_symlinks: bool = True):
        if path == state:
            raise PermissionError("Transient metadata failure")
        return stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", intermittent)
    degraded = signals.snapshot()
    assert degraded == baseline

    monkeypatch.setattr(Path, "stat", stat)
    with engine.begin() as connection:
        connection.execute(
            account_state.update().where(account_state.c.key == "test").values(value_json='"after"')
        )
    assert signals.snapshot().jobs != baseline.jobs
    engine.dispose()
