from __future__ import annotations

from prompta.conversation_reconciliation import (
    RecoveryAction,
    advance_completion_poll,
    assess_snapshot_completion,
    delivery_failure_action,
    final_text_recovery_decision,
    transient_recovery_decision,
)


def _durable_user(message_key: str = "u2", content: str = "Latest question") -> dict[str, object]:
    return {
        "message_key": message_key,
        "role": "user",
        "content": content,
    }


def test_completion_assessment_requires_snapshot_to_contain_latest_durable_user() -> None:
    completion = assess_snapshot_completion(
        {
            "streaming": False,
            "messages": [
                {"id": "u1", "role": "user", "content": "Older question"},
                {"id": "a1", "role": "assistant", "content": "Older answer"},
            ],
        },
        [_durable_user()],
        {"complete": True, "turn_ended": True},
        completion_hint=True,
        failure_hint=False,
        completion_polls=3,
        fallback_completion_polls=10,
    )

    assert completion.waiting_for_latest_assistant is True
    assert completion.snapshot_has_latest_user is False
    assert completion.has_assistant is False
    assert completion.missing_latest_assistant is False


def test_completion_assessment_marks_completed_turn_missing_latest_assistant() -> None:
    completion = assess_snapshot_completion(
        {
            "streaming": False,
            "messages": [
                {"id": "u2", "role": "user", "content": "Latest question"},
            ],
        },
        [_durable_user()],
        {"complete": True, "turn_ended": True},
        completion_hint=True,
        failure_hint=False,
        completion_polls=3,
        fallback_completion_polls=10,
    )

    assert completion.snapshot_has_latest_user is True
    assert completion.has_assistant is False
    assert completion.missing_latest_assistant is True
    assert completion.missing_final_text is True
    assert completion.completion_polls == 3


def test_completion_assessment_accepts_latest_user_by_text_when_id_changes() -> None:
    completion = assess_snapshot_completion(
        {
            "streaming": False,
            "messages": [
                {"id": "different-id", "role": "user", "content": "Latest question"},
                {"id": "a2", "role": "assistant", "content": "Final answer"},
            ],
        },
        [_durable_user()],
        {"complete": True, "turn_ended": True},
        completion_hint=True,
        failure_hint=False,
        completion_polls=3,
        fallback_completion_polls=10,
    )

    assert completion.snapshot_has_latest_user is True
    assert completion.has_assistant is True
    assert completion.missing_latest_assistant is False
    assert completion.missing_final_text is False


def test_advance_completion_poll_is_a_deterministic_state_transition() -> None:
    assert advance_completion_poll(
        idle_polls=2,
        settled_at=0.0,
        changed=False,
        completion_hint=True,
        streaming=False,
        has_assistant=True,
        missing_latest_assistant=False,
    ) == (3, 0.0)

    assert advance_completion_poll(
        idle_polls=5,
        settled_at=12.5,
        changed=True,
        completion_hint=True,
        streaming=False,
        has_assistant=True,
        missing_latest_assistant=False,
    ) == (5, 12.5)

    assert advance_completion_poll(
        idle_polls=5,
        settled_at=0.0,
        changed=True,
        completion_hint=True,
        streaming=False,
        has_assistant=True,
        missing_latest_assistant=False,
    ) == (0, 0.0)


def test_transient_recovery_decision_uses_recovered_activity_and_escalates() -> None:
    waiting = transient_recovery_decision(
        now_epoch=100.0,
        transient_since_epoch=0.0,
        recovered_cache_updated_at=90.0,
        recovery_attempts=0,
        recovery_delay_seconds=30.0,
        failure_timeout_seconds=900.0,
    )
    assert waiting.action is RecoveryAction.WAIT
    assert waiting.transient_since_epoch == 90.0

    reload = transient_recovery_decision(
        now_epoch=121.0,
        transient_since_epoch=0.0,
        recovered_cache_updated_at=90.0,
        recovery_attempts=0,
        recovery_delay_seconds=30.0,
        failure_timeout_seconds=900.0,
    )
    assert reload.action is RecoveryAction.RELOAD
    assert reload.transient_since_epoch == 90.0

    interrupt = transient_recovery_decision(
        now_epoch=1021.0,
        transient_since_epoch=121.0,
        recovered_cache_updated_at=0.0,
        recovery_attempts=1,
        recovery_delay_seconds=30.0,
        failure_timeout_seconds=900.0,
    )
    assert interrupt.action is RecoveryAction.INTERRUPT


def _delivery_action(
    *,
    idle_polls: int,
    retry_attempts: int = 0,
    retry_at: float = 0.0,
    recovery_attempts: int = 0,
    recovery_at: float = 0.0,
    retry_control_failed: bool = False,
) -> RecoveryAction:
    return delivery_failure_action(
        now_monotonic=100.0,
        idle_polls=idle_polls,
        retry_attempts=retry_attempts,
        retry_at=retry_at,
        recovery_attempts=recovery_attempts,
        recovery_at=recovery_at,
        failure_polls=3,
        retry_discovery_polls=3,
        retry_max_attempts=1,
        retry_grace_seconds=15.0,
        recovery_max_attempts=1,
        recovery_grace_seconds=15.0,
        retry_control_failed=retry_control_failed,
    )


def test_delivery_failure_action_keeps_retry_and_reload_policy_explicit() -> None:
    assert _delivery_action(idle_polls=2) is RecoveryAction.WAIT
    assert _delivery_action(idle_polls=3) is RecoveryAction.RETRY
    assert _delivery_action(idle_polls=5, retry_control_failed=True) is RecoveryAction.WAIT
    assert _delivery_action(idle_polls=6, retry_control_failed=True) is RecoveryAction.RELOAD

    assert _delivery_action(idle_polls=6, retry_attempts=1, retry_at=90.0) is RecoveryAction.WAIT
    assert _delivery_action(idle_polls=6, retry_attempts=1, retry_at=80.0) is RecoveryAction.RELOAD

    assert (
        _delivery_action(
            idle_polls=6,
            retry_attempts=1,
            recovery_attempts=1,
            recovery_at=80.0,
        )
        is RecoveryAction.INTERRUPT
    )


def test_final_text_recovery_decision_reloads_then_waits_then_interrupts() -> None:
    first = final_text_recovery_decision(
        now_epoch=100.0,
        missing_since_epoch=0.0,
        recovery_attempts=0,
        max_recovery_attempts=1,
        failure_timeout_seconds=120.0,
    )
    assert first.action is RecoveryAction.RELOAD
    assert first.missing_since_epoch == 100.0
    assert first.timeout_expired is False

    waiting = final_text_recovery_decision(
        now_epoch=150.0,
        missing_since_epoch=100.0,
        recovery_attempts=1,
        max_recovery_attempts=1,
        failure_timeout_seconds=120.0,
    )
    assert waiting.action is RecoveryAction.WAIT

    expired = final_text_recovery_decision(
        now_epoch=220.0,
        missing_since_epoch=100.0,
        recovery_attempts=1,
        max_recovery_attempts=1,
        failure_timeout_seconds=120.0,
    )
    assert expired.action is RecoveryAction.INTERRUPT
    assert expired.timeout_expired is True
