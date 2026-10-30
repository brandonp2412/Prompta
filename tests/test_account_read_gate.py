"""Account-global read cooldown shared between the backup and live readers."""

from __future__ import annotations

from pathlib import Path

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

    # One failed page may issue several 429 responses; do not stack attempts.
    second = backup.note_http_429("900")
    assert 0 < second <= first
    assert live.read_backoff_status()[1] == 1


def test_missing_retry_after_uses_shared_default(tmp_path: Path) -> None:
    gate = AccountReadGate(tmp_path / "runtime.sqlite3")
    assert gate.note_http_429() >= 300
