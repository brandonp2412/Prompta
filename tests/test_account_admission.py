from __future__ import annotations

from pathlib import Path

from prompta.rate_limit import RateLimitError
from prompta.scheduler_runtime import SchedulerRuntime


def test_account_throttle_enter_and_clear_are_durable_across_workers(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime.sqlite3"
    delivery_runtime = SchedulerRuntime(state_path, state_path)
    conversation_runtime = SchedulerRuntime(state_path, state_path)

    delay = delivery_runtime.record_global_rate_limit(
        RateLimitError("history limited", retry_after=60)
    )

    assert delay >= 60
    status = conversation_runtime.account_admission_status()
    assert status["blocked"] is True
    assert status["kind"] == "rate_limit"
    assert status["reason"] == "history limited"
    assert conversation_runtime.global_backoff_remaining() > 0

    conversation_runtime.clear_global_rate_limit()

    assert delivery_runtime.global_backoff_remaining() == 0
    assert delivery_runtime.account_admission_status() == {
        "blocked": False,
        "kind": "",
        "reason": "",
        "retry_after_seconds": 0,
        "retry_at_epoch": 0.0,
    }
