from __future__ import annotations

from prompta.conversation_reconciliation import advance_completion_poll, assess_snapshot_completion


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
