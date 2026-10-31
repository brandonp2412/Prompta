from __future__ import annotations

from pathlib import Path

from prompta.response_store import ResponseStore


def test_browser_security_pause_never_shortens_a_durable_deadline(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    store.pause_history_recovery_security(until=1000, now=100)
    assert store.history_recovery_security_pause_remaining(now=100) == 900

    store.pause_history_recovery_security(until=400, now=101)
    assert store.history_recovery_security_pause_remaining(now=101) == 899

    store.pause_history_recovery_security(until=1500, now=102)
    assert store.history_recovery_security_pause_remaining(now=102) == 1398
