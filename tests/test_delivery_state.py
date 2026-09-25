from __future__ import annotations

import pytest

from prompta.delivery_state import (
    CompletionAction,
    FailureKind,
    claimable_delivery,
    coalesce_queued_reply,
    completion_action,
    decide_failure_transition,
    existing_client_job,
    expired_running_lease,
    normalize_recovery_status,
    renewable_delivery_lease,
    should_cleanup_attachments,
)


def test_claimability_is_deterministic_at_retry_and_lease_boundaries() -> None:
    assert claimable_delivery({"status": "queued"}, now=10.0)
    assert not claimable_delivery(
        {"status": "retrying", "retry_at": 10.1},
        now=10.0,
    )
    assert claimable_delivery(
        {"status": "retrying", "retry_at": 10.0},
        now=10.0,
    )
    assert claimable_delivery(
        {"status": "rate_limited", "retry_at": 10.0},
        now=10.0,
    )
    assert not claimable_delivery(
        {"status": "running", "lease_expires_at": 10.1},
        now=10.0,
    )
    assert claimable_delivery(
        {"status": "running", "lease_expires_at": 10.0},
        now=10.0,
    )
    assert not claimable_delivery({"status": "succeeded"}, now=10.0)


def test_renewal_requires_current_owner_and_unexpired_running_lease() -> None:
    record = {
        "status": "running",
        "lease_owner": "worker-a",
        "lease_expires_at": 20.0,
    }

    assert renewable_delivery_lease(record, owner="worker-a", now=19.9)
    assert not renewable_delivery_lease(record, owner="worker-b", now=19.9)
    assert not renewable_delivery_lease(record, owner="worker-a", now=20.0)


def test_completion_distinguishes_commit_duplicate_ack_and_rejection() -> None:
    assert (
        completion_action(
            {"status": "running", "lease_owner": "worker-a"},
            owner="worker-a",
        )
        is CompletionAction.COMPLETE
    )
    assert (
        completion_action(
            {"status": "succeeded", "lease_owner": ""},
            owner="stale-worker",
        )
        is CompletionAction.ACKNOWLEDGE
    )
    assert (
        completion_action(
            {"status": "running", "lease_owner": "worker-a"},
            owner="worker-b",
        )
        is CompletionAction.REJECT
    )
    assert (
        completion_action(
            {"status": "outcome_unknown", "lease_owner": ""},
            owner="worker-a",
        )
        is CompletionAction.REJECT
    )


def test_generic_failure_retries_then_dead_letters_at_existing_attempt_limit() -> None:
    retry = decide_failure_transition(
        kind=FailureKind.GENERIC,
        now=100.0,
        error="temporary",
        generic_attempt=0,
        infrastructure_attempt=0,
        max_generic_attempts=5,
        retry_base_seconds=2.0,
        retry_cap_seconds=60.0,
    )
    assert retry.status == "retrying"
    assert retry.retry_attempt == 1
    assert retry.retry_at == 102.0
    assert retry.retry_after_seconds == 2
    assert retry.retries
    assert not retry.terminal

    final = decide_failure_transition(
        kind=FailureKind.GENERIC,
        now=200.0,
        error="still broken",
        generic_attempt=4,
        infrastructure_attempt=2,
        max_generic_attempts=5,
        retry_base_seconds=2.0,
        retry_cap_seconds=60.0,
    )
    assert final.status == "dead_lettered"
    assert final.retry_attempt == 5
    assert final.infrastructure_retry_attempt == 2
    assert final.retry_at == 0.0
    assert final.terminal


def test_infrastructure_and_deferred_retries_do_not_consume_generic_attempts() -> None:
    infrastructure = decide_failure_transition(
        kind=FailureKind.INFRASTRUCTURE,
        now=50.0,
        error="browser unavailable",
        generic_attempt=3,
        infrastructure_attempt=2,
        max_generic_attempts=5,
        retry_base_seconds=2.0,
        retry_cap_seconds=60.0,
    )
    assert infrastructure.status == "retrying"
    assert infrastructure.retry_attempt == 3
    assert infrastructure.infrastructure_retry_attempt == 3
    assert infrastructure.retry_at == 58.0

    deferred = decide_failure_transition(
        kind=FailureKind.DEFERRED,
        now=50.0,
        error="busy",
        generic_attempt=3,
        infrastructure_attempt=2,
        max_generic_attempts=5,
        retry_base_seconds=2.0,
        retry_cap_seconds=60.0,
        delay_seconds=12.25,
    )
    assert deferred.status == "retrying"
    assert deferred.retry_attempt == 3
    assert deferred.infrastructure_retry_attempt == 2
    assert deferred.retry_at == pytest.approx(62.25)
    assert deferred.retry_after_seconds == 13


def test_rate_limit_and_uncertain_outcome_transitions_preserve_duplicate_protection() -> None:
    limited = decide_failure_transition(
        kind=FailureKind.RATE_LIMITED,
        now=100.0,
        error="rate limited",
        generic_attempt=2,
        infrastructure_attempt=1,
        max_generic_attempts=5,
        retry_base_seconds=2.0,
        retry_cap_seconds=60.0,
        delay_seconds=90.0,
        rate_limit_attempt=4,
    )
    assert limited.status == "rate_limited"
    assert limited.retry_attempt == 4
    assert limited.retry_at == 190.0

    uncertain = decide_failure_transition(
        kind=FailureKind.OUTCOME_UNKNOWN,
        now=123.0,
        error="send may have succeeded",
        generic_attempt=2,
        infrastructure_attempt=1,
        max_generic_attempts=5,
        retry_base_seconds=2.0,
        retry_cap_seconds=60.0,
    )
    assert uncertain.status == "outcome_unknown"
    assert uncertain.finished_at == 123.0
    assert uncertain.terminal
    assert not uncertain.retries


def test_recovery_normalization_preserves_known_states_and_defaults_legacy_rows() -> None:
    assert normalize_recovery_status("", retry_at=0.0, retry_attempt=0) == "queued"
    assert normalize_recovery_status("", retry_at=30.0, retry_attempt=0) == "rate_limited"
    assert normalize_recovery_status("", retry_at=0.0, retry_attempt=2) == "rate_limited"
    assert normalize_recovery_status("running", retry_at=0.0, retry_attempt=0) == "running"
    assert (
        normalize_recovery_status("outcome_unknown", retry_at=0.0, retry_attempt=0)
        == "outcome_unknown"
    )
    assert normalize_recovery_status("obsolete", retry_at=0.0, retry_attempt=0) == "queued"
    assert expired_running_lease("running", lease_expires_at=10.0, now=10.0)
    assert not expired_running_lease("running", lease_expires_at=10.1, now=10.0)


def test_coalescing_is_a_pure_first_queued_reply_decision() -> None:
    jobs = [
        {
            "send_id": "running",
            "operation": "reply",
            "conversation_id": "chat-1",
            "status": "running",
            "message": "already sending",
            "_attachments": ["old-running.txt"],
        },
        {
            "send_id": "queued",
            "operation": "reply",
            "conversation_id": "chat-1",
            "status": "queued",
            "message": "first pending",
            "_attachments": ["old.txt"],
            "client_id": "primary",
            "created_at": 12.0,
        },
    ]

    decision = coalesce_queued_reply(
        jobs,
        conversation_id="chat-1",
        message="second pending",
        attachments=["new.txt"],
    )

    assert decision is not None
    assert decision.send_id == "queued"
    assert decision.primary_client_id == "primary"
    assert decision.message == "first pending\nsecond pending"
    assert decision.attachments == ("old.txt", "new.txt")
    assert jobs[1]["message"] == "first pending"


def test_client_idempotency_lookup_and_attachment_cleanup_policy_are_pure() -> None:
    jobs = {"send-1": {"send_id": "send-1", "status": "succeeded"}}
    assert existing_client_job("client-1", {"client-1": "send-1"}, jobs) == jobs["send-1"]
    assert existing_client_job("", {"client-1": "send-1"}, jobs) is None
    assert not should_cleanup_attachments("outcome_unknown")
    assert not should_cleanup_attachments("dead_lettered")
    assert should_cleanup_attachments("succeeded")
    assert should_cleanup_attachments("")
