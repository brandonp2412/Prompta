from __future__ import annotations

import hashlib
from datetime import datetime

import pytest

from prompta.jobs import PromptJob, normalise_job_definition
from prompta.scheduler_policy import (
    due_in,
    failure_retry_remaining,
    failure_state_updates,
    initial_due_at,
    initial_jitter_window,
    next_due_at,
    occurrence_key,
    pending_delivery_updates,
    recurring_delay,
    recurring_jitter_cap,
    retry_at,
    send_gap_remaining,
    should_enqueue_job,
    successful_delivery_updates,
    terminal_reconciliation_updates,
)


def _expected_occurrence_key(job: PromptJob, marker: float) -> str:
    prompt_digest = hashlib.sha256(job.prompt.encode()).hexdigest()
    raw = f"{job.name}\0{prompt_digest}\0{marker:.6f}"
    return hashlib.sha256(raw.encode()).hexdigest()


def test_initial_due_time_uses_explicit_jitter_and_existing_state_short_circuits() -> None:
    job = PromptJob("interval", "work", 7200)

    assert initial_jitter_window(job) == pytest.approx(1800.0)
    assert initial_due_at(job, {}, now=1000.0, jitter_seconds=321.0) == pytest.approx(1321.0)
    assert (
        initial_due_at(
            job,
            {"initial_due_at_epoch": 1200.0},
            now=1000.0,
            jitter_seconds=999.0,
        )
        is None
    )


def test_initial_due_time_preserves_one_time_and_daily_semantics() -> None:
    one_time = PromptJob("once", "work", 0, run_at_epoch=2500.0)
    assert initial_due_at(one_time, {}, now=1000.0, jitter_seconds=999.0) == 2500.0

    daily = PromptJob("daily", "work", daily_at="07:00")
    now = datetime(2026, 9, 12, 6, 30).timestamp()
    expected = datetime(2026, 9, 12, 7, 0).timestamp()
    assert initial_due_at(daily, {}, now=now, jitter_seconds=999.0) == pytest.approx(expected)


def test_recurring_delay_uses_explicit_jitter_but_exact_interval_ignores_it() -> None:
    jittered = PromptJob("jittered", "work", 1800)
    exact = PromptJob("exact", "work", 1800, exact_interval=True)

    assert recurring_jitter_cap(jittered) == pytest.approx(300.0)
    assert recurring_delay(jittered, jitter_seconds=240.0) == pytest.approx(2040.0)
    assert recurring_jitter_cap(exact) == 0.0
    assert recurring_delay(exact, jitter_seconds=240.0) == pytest.approx(1800.0)


def test_job_definition_normalisation_is_pure_and_clamps_interval() -> None:
    job = normalise_job_definition(
        "  finite  ",
        "work",
        -10,
        "07:05",
        True,
        1234.0,
        "ABCDEF",
    )

    assert job == PromptJob(
        "finite",
        "work",
        0.0,
        "07:05",
        True,
        1234.0,
        "abcdef",
    )


def test_due_in_prefers_next_due_after_confirmed_send_and_uncertain_marker_otherwise() -> None:
    job = PromptJob("job", "work", 1800)
    confirmed = {
        "last_sent_at": 1000.0,
        "last_uncertain_send_at": 0.0,
        "next_due_at_epoch": 2500.0,
    }
    uncertain = {
        "last_sent_at": 900.0,
        "last_uncertain_send_at": 1000.0,
        "next_due_at_epoch": 5000.0,
    }

    assert due_in(job, confirmed, now=1500.0) == pytest.approx(1000.0)
    assert due_in(job, uncertain, now=1300.0) == pytest.approx(1500.0)


def test_due_in_preserves_immediately_due_behavior_for_corrupt_schedule_state() -> None:
    job = PromptJob("job", "work", 1800)
    assert (
        due_in(
            job,
            {
                "last_sent_at": 1000.0,
                "last_uncertain_send_at": 0.0,
                "next_due_at_epoch": "corrupt",
                "initial_due_at_epoch": 0.0,
            },
            now=1100.0,
        )
        == 0.0
    )


def test_occurrence_key_uses_same_duplicate_protection_marker_as_scheduler() -> None:
    job = PromptJob("job", "work", 1800)
    state = {
        "last_sent_at": 900.0,
        "last_uncertain_send_at": 1000.0,
        "next_due_at_epoch": 5000.0,
    }
    assert occurrence_key(job, state) == _expected_occurrence_key(job, 1000.0)

    one_time = PromptJob("once", "one shot", 0, run_at_epoch=2345.0)
    assert occurrence_key(one_time, {"initial_due_at_epoch": 9999.0}) == _expected_occurrence_key(
        one_time,
        2345.0,
    )


@pytest.mark.parametrize(
    ("state", "now", "pending_delivery", "expected"),
    [
        ({}, 1000.0, False, True),
        ({"paused": True}, 1000.0, False, False),
        ({"initial_due_at_epoch": 1200.0}, 1000.0, False, False),
        ({"initial_due_at_epoch": 1000.0}, 1000.0, False, True),
        ({}, 1000.0, True, False),
    ],
)
def test_enqueue_decision_is_pure(
    state: dict[str, object],
    now: float,
    pending_delivery: bool,
    expected: bool,
) -> None:
    job = PromptJob("job", "work", 1800)
    assert (
        should_enqueue_job(
            job,
            state,
            now=now,
            pending_delivery=pending_delivery,
        )
        is expected
    )


def test_next_due_time_handles_one_time_daily_and_interval_from_explicit_inputs() -> None:
    assert (
        next_due_at(
            completed_at=1000.0,
            one_time=True,
            daily_at=None,
            interval_seconds=1800.0,
            exact_interval=False,
            jitter_seconds=240.0,
        )
        == 0.0
    )
    assert next_due_at(
        completed_at=1000.0,
        one_time=False,
        daily_at=None,
        interval_seconds=1800.0,
        exact_interval=False,
        jitter_seconds=240.0,
    ) == pytest.approx(3040.0)

    completed = datetime(2026, 9, 12, 7, 0).timestamp()
    next_day = datetime(2026, 9, 13, 7, 0).timestamp()
    assert next_due_at(
        completed_at=completed,
        one_time=False,
        daily_at="07:00",
        interval_seconds=0.0,
        exact_interval=False,
        jitter_seconds=999.0,
    ) == pytest.approx(next_day)


def test_terminal_reconciliation_returns_complete_success_transition() -> None:
    state = {
        "pending_delivery_prompt_sha256": "digest",
        "pending_delivery_interval_seconds": 60.0,
        "pending_delivery_daily_at": "",
        "pending_delivery_exact_interval": False,
        "pending_delivery_one_time": False,
    }
    receipt = {
        "send_id": "scheduled-1",
        "status": "succeeded",
        "conversation_id": "conversation-1",
        "finished_at": 1005.0,
    }

    updates = terminal_reconciliation_updates(
        state,
        receipt,
        fallback_completed_at=9999.0,
        jitter_seconds=12.0,
    )

    assert updates == {
        "initial_due_at_epoch": 0.0,
        "next_due_at_epoch": 1077.0,
        "last_completed_delivery_send_id": "scheduled-1",
        "status_at": 1005.0,
        "prompt_sha256": "digest",
        "last_sent_at": 1005.0,
        "last_uncertain_send_at": 0.0,
        "last_conversation_id": "conversation-1",
        "failure_retry_until_epoch": 0.0,
        "status": "healthy",
        "status_message": "",
    }


def test_terminal_reconciliation_is_idempotent_and_preserves_failure_message() -> None:
    state = {
        "last_completed_delivery_send_id": "old",
        "pending_delivery_interval_seconds": 60.0,
        "pending_delivery_exact_interval": True,
    }
    receipt = {
        "send_id": "scheduled-2",
        "status": "outcome_unknown",
        "last_error": "delivery uncertain",
        "updated_at": 2000.0,
    }
    updates = terminal_reconciliation_updates(
        state,
        receipt,
        fallback_completed_at=9999.0,
    )
    assert updates is not None
    assert updates["next_due_at_epoch"] == pytest.approx(2060.0)
    assert updates["status"] == "failing"
    assert updates["status_message"] == "delivery uncertain"

    completed_state = {**state, "last_completed_delivery_send_id": "scheduled-2"}
    assert (
        terminal_reconciliation_updates(
            completed_state,
            receipt,
            fallback_completed_at=9999.0,
        )
        is None
    )


def test_pending_delivery_metadata_is_derived_without_persistence() -> None:
    job = PromptJob(
        "daily",
        "work",
        1800,
        daily_at="07:00",
        exact_interval=True,
        source_revision="abc123",
    )
    assert pending_delivery_updates(
        job,
        send_id="scheduled-1",
        idempotency_key="key-1",
        queued_at=1000.0,
    ) == {
        "last_enqueued_at": 1000.0,
        "last_delivery_send_id": "scheduled-1",
        "last_delivery_idempotency_key": "key-1",
        "pending_delivery_prompt_sha256": hashlib.sha256(b"work").hexdigest(),
        "pending_delivery_interval_seconds": 1800.0,
        "pending_delivery_daily_at": "07:00",
        "pending_delivery_exact_interval": True,
        "pending_delivery_one_time": False,
        "status": "queued",
        "status_message": "",
        "status_at": 1000.0,
    }


def test_success_and_failure_state_updates_are_explicit_transitions() -> None:
    assert failure_state_updates(
        "network failed",
        status_at=1000.0,
        retry_until=1300.0,
    ) == {
        "status": "failing",
        "status_message": "network failed",
        "status_at": 1000.0,
        "failure_retry_until_epoch": 1300.0,
    }

    assert successful_delivery_updates(
        {"job_prompt_sha256": "digest"},
        conversation_id="conversation-1",
        sent_at=2000.0,
        next_due_at_epoch=3800.0,
        rate_limit_backoff={"attempt": 0},
    ) == {
        "prompt_sha256": "digest",
        "last_sent_at": 2000.0,
        "last_uncertain_send_at": 0.0,
        "initial_due_at_epoch": 0.0,
        "next_due_at_epoch": 3800.0,
        "last_conversation_id": "conversation-1",
        "rate_limit_backoff": {"attempt": 0},
        "failure_retry_until_epoch": 0.0,
        "status": "healthy",
        "status_message": "",
        "status_at": 2000.0,
    }


def test_retry_at_clamps_negative_delay_and_uses_explicit_time() -> None:
    assert retry_at(now=1000.0, delay_seconds=300.0) == 1300.0
    assert retry_at(now=1000.0, delay_seconds=-5.0) == 1000.0


def test_retry_and_send_gap_windows_use_explicit_time() -> None:
    assert send_gap_remaining(last_attempt_at=100.0, gap_seconds=60.0, now=125.0) == 35.0
    assert send_gap_remaining(last_attempt_at="bad", gap_seconds=60.0, now=125.0) == 0.0

    assert (
        failure_retry_remaining(
            persisted_retry_until=150.0,
            in_memory_retry_until=180.0,
            now=125.0,
        )
        == 55.0
    )
    assert (
        failure_retry_remaining(
            persisted_retry_until="bad",
            in_memory_retry_until=0.0,
            now=125.0,
        )
        == 0.0
    )
