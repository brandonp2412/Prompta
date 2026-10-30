"""Concurrent read-only recovery processes must share one atomic account navigation slot."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from test_history_recovery import FakeHistoryDriver, _expired

from prompta.history_recovery import HistoryRecovery
from prompta.response_store import ResponseStore
from prompta.scheduler_runtime import SchedulerRuntime


def test_concurrent_workers_cannot_reuse_the_same_history_read_slot(tmp_path: Path) -> None:
    path = tmp_path / "chat-results.sqlite3"
    initial = ResponseStore(path)
    _expired(initial, "manual-first")
    _expired(initial, "manual-second")
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    barrier = Barrier(2)

    class RacingStore(ResponseStore):
        def reserve_history_recovery_global_slot(self, *, now: float, interval: float) -> bool:
            # Both workers have already passed their separate preflight read.
            barrier.wait(timeout=10)
            return super().reserve_history_recovery_global_slot(now=now, interval=interval)

    drivers = [FakeHistoryDriver(), FakeHistoryDriver()]
    workers = [
        HistoryRecovery(RacingStore(path), runtime, lambda driver=driver: driver)
        for driver in drivers
    ]
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda worker: worker.recover_once(now=150), workers))

    assert results.count(True) == 1
    assert sum(driver.visited.count("connect") for driver in drivers) == 1
    assert initial.history_recovery_global_pace_remaining(now=151) == 89
    saved = [initial.get(send_id) for send_id in ("manual-first", "manual-second")]
    assert sum(record is not None and record["status"] == "completed" for record in saved) == 1
