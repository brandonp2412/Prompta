from __future__ import annotations

import base64
import sys
from http import HTTPStatus
from pathlib import Path

import pytest

from prompta.attachment_store import decode_attachments
from prompta.image_previews import preview_attachment_assignments
from prompta.jobs import PromptJob
from prompta.pinned_chats import (
    promote_pinned_state,
    seed_pinned_state,
    set_pinned_state,
)
from prompta.read_state import decorate_read_state
from prompta.web_decisions import (
    query_limit,
    resource_id,
    schedule_at_request,
    schedule_every_request,
    schedule_response,
    send_operation,
)
from prompta.web_jobs import (
    build_job_cli_command,
    matching_exact_interval_job,
    normalize_schedule_prompt,
    serialize_scheduled_jobs,
    validate_schedule_interval,
    validate_schedule_time,
)


def test_query_and_schedule_request_decisions_are_deterministic() -> None:
    assert query_limit({"limit": ["nope"]}, default=100, minimum=1, maximum=5000) == 100
    assert query_limit({"limit": ["0"]}, default=100, minimum=1, maximum=5000) == 1
    assert query_limit({"limit": ["9000"]}, default=100, minimum=1, maximum=5000) == 5000

    assert schedule_every_request({"prompt": "  work  ", "interval_minutes": "2.5"}) == (
        "work",
        2.5,
    )
    assert schedule_at_request(
        {"prompt": "  later  ", "run_at_epoch": "101"},
        now=100.0,
    ) == ("later", 101.0)

    with pytest.raises(ValueError, match="timestamp in the future"):
        schedule_at_request({"prompt": "later", "run_at_epoch": 100}, now=100.0)


def test_schedule_response_preserves_created_status_contract() -> None:
    assert schedule_response({"created": True, "name": "new"}) == (
        HTTPStatus.CREATED,
        {"ok": True, "created": True, "name": "new"},
    )
    assert schedule_response({"created": False, "name": "existing"}) == (
        HTTPStatus.OK,
        {"ok": True, "created": False, "name": "existing"},
    )


def test_resource_and_send_operation_decisions() -> None:
    assert resource_id("/api/chats/chat-1/messages", "/api/chats/", "/messages") == "chat-1"
    assert resource_id("/api/chats/chat-1", "/api/chats/", "/messages") is None
    assert resource_id("/api/sends//send-1//", "/api/sends/") == "send-1"

    assert send_operation(reply=False, track_response=False) == "once"
    assert send_operation(reply=False, track_response=True) == "once_tracked"
    assert send_operation(reply=True, track_response=False) == "reply"
    assert send_operation(reply=True, track_response=True) == "reply_tracked"


def test_job_cli_command_builder_is_pure_policy(tmp_path: Path) -> None:
    action, command, start_scheduler = build_job_cli_command(
        " ADD ",
        {
            "name": "hourly",
            "prompt": "Do work",
            "interval_minutes": "60",
            "exact_interval": True,
        },
        jobs_path=tmp_path / "jobs.sqlite3",
        state_path=tmp_path / "state.sqlite3",
    )

    assert action == "add"
    assert command == [
        sys.executable,
        "-m",
        "prompta.core",
        "add",
        "hourly",
        "Do work",
        "--interval-minutes",
        "60.0",
        "--exact-interval",
        "--jobs-file",
        str(tmp_path / "jobs.sqlite3"),
    ]
    assert start_scheduler is True
    assert not (tmp_path / "jobs.sqlite3").exists()


def test_schedule_policy_helpers_normalize_validate_and_deduplicate() -> None:
    assert normalize_schedule_prompt("  Fix   bugs\nnow  ") == "Fix bugs now"
    assert validate_schedule_interval(0.1) == 0.1
    assert validate_schedule_time(101, now=100) == 101.0

    with pytest.raises(ValueError, match="at least 6 seconds"):
        validate_schedule_interval(0.09)

    job = PromptJob(
        "existing",
        "Fix   Bugs",
        interval_seconds=1800,
        exact_interval=True,
        source_revision="abc",
    )
    assert (
        matching_exact_interval_job(
            [job],
            prompt="  fix bugs ",
            interval_seconds=1800.0000005,
        )
        is job
    )


def test_scheduled_job_serialization_normalizes_runtime_state() -> None:
    jobs = [
        PromptJob("paused-job", "A", 600, exact_interval=True),
        PromptJob("odd-job", "B", 1200),
    ]
    result = serialize_scheduled_jobs(
        jobs,
        {
            "paused-job": {
                "paused": True,
                "status": "healthy",
                "next_due_at_epoch": "123.5",
            },
            "odd-job": {
                "status": "mystery",
                "next_due_at_epoch": "not-a-number",
            },
        },
    )

    assert result[0]["paused"] is True
    assert result[0]["status"] == "paused"
    assert result[0]["next_due_at_epoch"] == 123.5
    assert result[1]["status"] == "pending"
    assert result[1]["next_due_at_epoch"] == 0.0


def test_pin_state_transitions_do_not_mutate_inputs() -> None:
    current = ["first", "second"]
    initialized, seeded, should_write = seed_pinned_state(True, current, ["ignored"])
    assert (initialized, seeded, should_write) == (True, ["first", "second"], False)

    initialized, pinned, should_write = set_pinned_state(False, current, "third", True)
    assert (initialized, pinned, should_write) == (True, ["first", "second", "third"], True)

    initialized, promoted, should_write = promote_pinned_state(True, current, "first", "second")
    assert (initialized, promoted, should_write) == (True, ["second"], True)
    assert current == ["first", "second"]


def test_read_state_decoration_is_pure() -> None:
    source = [{"id": "chat", "last_assistant_at": "12", "title": "Chat"}]
    result = decorate_read_state(source, baseline=10.0, read_at={"chat": 11.0})

    assert result == [{"id": "chat", "last_assistant_at": "12", "title": "Chat", "unread": True}]
    assert source == [{"id": "chat", "last_assistant_at": "12", "title": "Chat"}]


def test_preview_assignment_matches_nearest_unused_user_message() -> None:
    messages: list[object] = [
        {"role": "user", "content": "Look", "created_at": 10.0},
        {"role": "assistant", "content": "ok", "created_at": 11.0},
        {"role": "user", "content": "Look", "created_at": 20.0},
    ]
    records = [
        {
            "conversation_id": "chat",
            "message": "Look",
            "created_at": 19.0,
            "images": [{"id": "b" * 32, "name": "late.png", "type": "image/png"}],
        },
        {
            "conversation_id": "chat",
            "message": "Look",
            "created_at": 9.0,
            "images": [{"id": "a" * 32, "name": "early.png", "type": "image/png"}],
        },
    ]

    assignments = preview_attachment_assignments(messages, records, "chat")

    assert assignments == [
        (0, [{"id": "a" * 32, "name": "early.png", "type": "image/png"}]),
        (2, [{"id": "b" * 32, "name": "late.png", "type": "image/png"}]),
    ]
    assert all(isinstance(message, dict) and "attachments" not in message for message in messages)


def test_attachment_decoding_is_pure_and_accepts_data_urls(tmp_path: Path) -> None:
    content = b"hello"
    encoded = base64.b64encode(content).decode()
    result = decode_attachments(
        [
            {
                "name": "../note.txt",
                "type": " Text/Plain ",
                "data": f"data:text/plain;base64,{encoded}",
            }
        ]
    )

    assert result == [("note.txt", "text/plain", content)]
    assert list(tmp_path.iterdir()) == []
