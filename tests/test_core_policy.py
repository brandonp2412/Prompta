from __future__ import annotations

from unittest.mock import patch

from prompta.core import Prompta, PromptaConfig, PromptJob, _job_status
from prompta.rate_limit import RateLimitBackoff


def test_cli_job_status_preserves_legacy_state_precedence(tmp_path) -> None:
    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "jobs.json",
            state_path=tmp_path / "state.json",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    try:
        cases = [
            ({"paused": True, "status": "healthy"}, ("Ⅱ", "paused")),
            (
                {"status": "healthy", "status_message": "Rate limit reached"},
                ("⏳", "rate-limited"),
            ),
            ({"status": "failing", "last_sent_at": 123.0}, ("✗", "failing")),
            ({"status": "healthy"}, ("●", "healthy")),
            (
                {"rate_limit_backoff": {"attempts": "2"}},
                ("✗", "failing"),
            ),
            ({"last_uncertain_send_at": 456.0}, ("✗", "failing")),
            ({"last_sent_at": 789.0}, ("●", "healthy")),
            ({}, ("○", "pending")),
        ]

        for index, (state, expected) in enumerate(cases):
            job = PromptJob(name=f"lane-{index}", prompt="Do work")
            prompta._update_job_state(job.name, state)
            assert _job_status(prompta, job) == expected
    finally:
        prompta.cache.close()


def test_rate_limit_backoff_round_trip_keeps_wall_clock_deadlines() -> None:
    backoff = RateLimitBackoff()
    with patch("prompta.rate_limit.random.uniform", return_value=0.0):
        assert backoff.record(120.0, now=100.0) == 120.0

    snapshot = backoff.snapshot(now=110.0, wall_time=1_000.0)

    assert snapshot == {
        "attempts": 1,
        "blocked_until_epoch": 1_110.0,
        "last_limited_at_epoch": 990.0,
    }

    restored = RateLimitBackoff()
    restored.restore(snapshot, now=500.0, wall_time=1_050.0)

    assert restored.attempts == 1
    assert restored.blocked_until == 560.0
    assert restored.last_limited_at == 440.0
    assert restored.remaining(now=500.0) == 60.0


def test_rate_limit_restore_drops_expired_escalation_after_quiet_period() -> None:
    restored = RateLimitBackoff()

    restored.restore(
        {
            "attempts": 4,
            "blocked_until_epoch": 1_100.0,
            "last_limited_at_epoch": 1_000.0,
        },
        now=500.0,
        wall_time=3_000.0,
    )

    assert restored.attempts == 0
    assert restored.blocked_until == 0.0
    assert restored.last_limited_at == 0.0
