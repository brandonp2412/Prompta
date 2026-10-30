"""Transient local filesystem failure must not strand active SSE clients."""
from __future__ import annotations

from pathlib import Path

from prompta.live_events import LocalEventSignals


def test_live_revisions_continue_when_a_database_stat_fails(
    tmp_path: Path, monkeypatch,
) -> None:
    jobs = tmp_path / "jobs.sqlite3"
    state = tmp_path / "runtime.sqlite3"
    state.touch()
    signals = LocalEventSignals(jobs, state)
    baseline = signals.snapshot()
    stat = Path.stat

    def intermittent(path: Path, *, follow_symlinks: bool = True):
        if path == state:
            raise PermissionError("Transient metadata failure")
        return stat(path, follow_symlinks=follow_symlinks)

    monkeypatch.setattr(Path, "stat", intermittent)
    degraded = signals.snapshot()
    assert degraded.jobs != baseline.jobs
    assert degraded.jobs[2] == (0, 0, 0)

    monkeypatch.setattr(Path, "stat", stat)
    assert signals.snapshot() == baseline
