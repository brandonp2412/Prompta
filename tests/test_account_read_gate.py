"""Account-global read cooldown shared between the backup and live readers."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Barrier

from prompta.account_read_gate import AccountReadGate
from prompta.scheduler_runtime import SchedulerRuntime


def test_http_429_updates_existing_durable_account_backoff(tmp_path: Path) -> None:
    state = tmp_path / "runtime.sqlite3"
    backup = AccountReadGate(state)
    live = SchedulerRuntime(state, state)
    assert backup.remaining() == 0
    assert live.read_backoff_remaining() == 0

    first = backup.note_http_429("420")
    assert first >= 420
    assert live.read_backoff_remaining() > 400
    assert live.read_backoff_status()[1] == 1

    # A stricter server Retry-After extends safety without stacking attempts.
    second = backup.note_http_429("900")
    assert second > 899
    assert live.read_backoff_remaining() > 899
    assert live.read_backoff_status()[1] == 1

    # Repeated 429s without a longer deadline keep the original attempt count.
    third = backup.note_http_429()
    assert 0 < third <= second
    assert live.read_backoff_status()[1] == 1


def test_missing_retry_after_uses_shared_default(tmp_path: Path) -> None:
    gate = AccountReadGate(tmp_path / "runtime.sqlite3")
    assert gate.note_http_429() >= 300


def test_concurrent_account_read_429s_share_one_attempt_and_longest_pause(
    tmp_path: Path,
) -> None:
    path = tmp_path / "runtime.sqlite3"
    gates = [AccountReadGate(path) for _ in range(3)]
    barrier = Barrier(3)

    def report(index: int) -> float:
        barrier.wait(timeout=10)
        return gates[index].note_http_429(str(600 + 300 * index))

    with ThreadPoolExecutor(max_workers=3) as pool:
        delays = list(pool.map(report, range(3)))

    assert all(delay > 0 for delay in delays)
    remaining, attempts = SchedulerRuntime(path, path).read_backoff_status()
    assert remaining > 1190
    assert attempts == 1
