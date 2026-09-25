from __future__ import annotations

from prompta.snapshot_reconciliation import (
    IncomingMessage,
    classify_snapshot_coverage,
    incoming_messages,
    normalize_snapshot_messages,
    resolve_streaming_message_key,
    select_handoff_candidate,
    snapshot_message_status,
)


def _row(
    message_key: str,
    ordinal: int,
    role: str,
    content: str,
    *,
    status: str = "complete",
    updated_at: float = 1.0,
) -> dict[str, object]:
    return {
        "message_key": message_key,
        "ordinal": ordinal,
        "role": role,
        "content": content,
        "status": status,
        "updated_at": updated_at,
    }


def test_normalize_snapshot_messages_is_pure_and_prefers_completed_structured_text() -> None:
    snapshot = {
        "messages": [
            {"id": "u1", "role": "user", "content": "Do work"},
            {"id": "a1", "role": "assistant", "content": "Corrupt merged final text"},
        ],
        "source_events": [
            {
                "id": "a1:dom-prose",
                "role": "assistant",
                "recipient": "all",
                "content_type": "text",
                "parts": ["Visible progress"],
                "create_time": 1.0,
                "end_turn": None,
            },
            {
                "id": "a1",
                "role": "assistant",
                "recipient": "all",
                "content_type": "text",
                "parts": ["Canonical final answer"],
                "create_time": 2.0,
                "end_turn": True,
            },
        ],
    }

    messages, events = normalize_snapshot_messages(snapshot, complete=True)

    assert messages[-1]["content"] == "Canonical final answer"
    assert events == snapshot["source_events"]
    assert snapshot["messages"][-1]["content"] == "Corrupt merged final text"


def test_incoming_messages_removes_ui_noise_and_skips_request_placeholders() -> None:
    messages = [
        {"id": "u1", "role": "user", "content": "Do work"},
        {
            "id": "request-placeholder-1",
            "role": "assistant",
            "content": "Waiting for response",
        },
        {
            "id": "a1",
            "role": "assistant",
            "content": "Done\n\nConnection interrupted. Waiting for the complete answer",
        },
    ]

    incoming = incoming_messages(messages)

    assert [(message.message_key, message.content) for message in incoming] == [
        ("u1", "Do work"),
        ("a1", "Done"),
    ]


def test_snapshot_coverage_collapses_only_missing_same_turn_assistant_siblings() -> None:
    existing = [
        _row("u1", 0, "user", "Do work"),
        _row("a1-tool", 1, "assistant", "Called tool"),
        _row("a1-final", 2, "assistant", "Finished"),
        _row("u2", 3, "user", "Next"),
        _row("a2", 4, "assistant", "Second answer"),
    ]
    incoming = (
        IncomingMessage(0, "user", "Do work", "u1"),
        IncomingMessage(1, "assistant", "Finished", "a1-final"),
        IncomingMessage(2, "user", "Next", "u2"),
        IncomingMessage(3, "assistant", "Second answer", "a2"),
    )

    coverage = classify_snapshot_coverage(incoming, existing)

    assert coverage.is_full is True
    assert coverage.superseded_stable_keys == frozenset({"a1-tool"})


def test_snapshot_coverage_marks_missing_only_assistant_as_partial() -> None:
    existing = [
        _row("u1", 0, "user", "First"),
        _row("a1", 1, "assistant", "First answer"),
        _row("u2", 2, "user", "Second"),
        _row("a2", 3, "assistant", "Second answer"),
    ]
    incoming = (
        IncomingMessage(0, "user", "First", "u1"),
        IncomingMessage(1, "user", "Second", "u2"),
        IncomingMessage(2, "assistant", "Second answer", "a2"),
    )

    coverage = classify_snapshot_coverage(incoming, existing)

    assert coverage.is_full is False
    assert coverage.superseded_stable_keys == frozenset()


def test_streaming_message_key_reuses_matching_durable_assistant_identity() -> None:
    current = {
        "u1": _row("u1", 0, "user", "Do work"),
        "a1": _row("a1", 1, "assistant", "Working"),
    }
    message = IncomingMessage(
        snapshot_index=1,
        role="assistant",
        content="Working and nearly done",
        message_key="__prompta_live_assistant_new__",
    )

    assert (
        resolve_streaming_message_key(
            message,
            preceding_user_key="u1",
            current_by_key=current,
        )
        == "a1"
    )


def test_handoff_selection_prefers_live_streaming_candidate() -> None:
    durable = _row("old-a1", 1, "assistant", "Older durable answer", updated_at=9.0)
    live = _row(
        "__prompta_live_assistant_1__",
        1,
        "assistant",
        "Visible progress",
        status="streaming",
        updated_at=2.0,
    )
    current = {
        "u1": _row("u1", 0, "user", "Do work"),
        "old-a1": durable,
        "__prompta_live_assistant_1__": live,
    }

    selected = select_handoff_candidate(
        role="assistant",
        message_key="final-a1",
        existing=None,
        preceding_user_key="u1",
        current_by_key=current,
    )

    assert selected is live


def test_snapshot_message_status_only_streams_the_last_visible_assistant() -> None:
    assistant = IncomingMessage(2, "assistant", "Working", "a1")
    earlier_assistant = IncomingMessage(1, "assistant", "Earlier", "a0")

    assert (
        snapshot_message_status(
            assistant,
            message_count=3,
            complete=False,
            streaming=True,
        )
        == "streaming"
    )
    assert (
        snapshot_message_status(
            earlier_assistant,
            message_count=3,
            complete=False,
            streaming=True,
        )
        == "complete"
    )
    assert (
        snapshot_message_status(
            assistant,
            message_count=3,
            complete=True,
            streaming=True,
        )
        == "complete"
    )
