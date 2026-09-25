from __future__ import annotations

from unittest.mock import patch

import pytest

from prompta.control_server import (
    ControlDeferredError,
    control_error_response,
    parse_control_request,
)
from prompta.core import Prompta, PromptaConfig, PromptJob, _job_status, _job_status_from_state
from prompta.rate_limit import (
    RateLimitBackoff,
    RateLimitError,
    RateLimitState,
    transition_rate_limit_backoff,
)
from prompta.resource_pressure import ResourceLimits, resource_limits_for_admission
from prompta.service_health import build_service_health_snapshot


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


def test_cli_job_status_function_is_independent_of_runtime_state() -> None:
    assert _job_status_from_state({"status_message": "RATE-LIMITED by account"}) == (
        "⏳",
        "rate-limited",
    )
    assert _job_status_from_state({"rate_limit_backoff": {"attempts": "invalid"}}) == (
        "○",
        "pending",
    )


def test_rate_limit_transition_receives_randomness_as_input() -> None:
    state, delay = transition_rate_limit_backoff(
        RateLimitState(),
        0.0,
        now=100.0,
        jitter_fraction=0.5,
    )

    assert delay == 315.0
    assert state == RateLimitState(attempts=1, blocked_until=415.0, last_limited_at=100.0)


def test_resource_hysteresis_limits_are_purely_derived() -> None:
    limits = ResourceLimits()

    assert resource_limits_for_admission(limits, blocked=False) is limits
    adjusted = resource_limits_for_admission(limits, blocked=True)
    assert adjusted.min_available_memory_fraction == 0.25
    assert adjusted.max_load_per_cpu == 0.75
    assert adjusted.max_cpu_psi_some_avg10 == 37.5
    assert adjusted.max_memory_psi_some_avg10 == 15.0
    assert adjusted.max_memory_psi_full_avg10 == 7.5
    assert adjusted.min_swap_free_fraction == pytest.approx(0.15)


def test_control_request_policy_is_pure_and_filters_attachments() -> None:
    request = parse_control_request(
        {
            "op": "reply",
            "conversation_id": "chat-1",
            "prompt": "Continue",
            "attachments": ["one.png", "", 42, " two.txt "],
            "defer_if_busy": True,
        }
    )

    assert request.op == "reply"
    assert request.conversation_id == "chat-1"
    assert request.prompt == "Continue"
    assert request.attachments == ("one.png", " two.txt ")
    assert request.defer_if_busy is True


def test_control_error_policy_preserves_retry_metadata() -> None:
    assert control_error_response(ControlDeferredError("busy", retry_after=3.5)) == {
        "ok": False,
        "error": "busy",
        "error_type": "deferred",
        "retry_after": 3.5,
    }
    assert control_error_response(RateLimitError("limited", retry_after=45)) == {
        "ok": False,
        "error": "limited",
        "error_type": "rate_limit",
        "retry_after": 45,
    }


def test_service_health_snapshot_is_derived_without_database_access() -> None:
    snapshot = build_service_health_snapshot(
        [
            {
                "service": "scheduler",
                "heartbeat_at": 90.0,
                "activity": "tick",
                "activity_started_at": 95.0,
            }
        ],
        now=100.0,
        stale_after_seconds={"scheduler": 20.0, "browser": 30.0},
    )

    assert snapshot["scheduler"] == {
        "heartbeat_at": 90.0,
        "heartbeat_age_seconds": 10.0,
        "stale_after_seconds": 20.0,
        "stale": False,
        "activity": "tick",
        "activity_started_at": 95.0,
        "activity_age_seconds": 5.0,
    }
    assert snapshot["browser"]["stale"] is True
    assert snapshot["browser"]["heartbeat_age_seconds"] is None


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
