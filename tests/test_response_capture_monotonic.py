from __future__ import annotations

from pathlib import Path
from typing import Literal

from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore

CONVERSATION = "12345678-1234-4123-8123-123456789abc"
MESSAGE = "23456789-1234-4123-8123-123456789abc"
PARENT = "34567890-1234-4123-8123-123456789abc"


def _accepted(tmp_path: Path) -> ResponseStore:
    store = ResponseStore(tmp_path / "results.sqlite3")
    store.ensure_queued("manual-1", "Private prompt", now=10)
    assert store.accept("manual-1", "123:owner", deadline=300, now=11)
    return store


def _capture(status: Literal["partial", "complete"], text: str) -> CaptureResult:
    return CaptureResult(
        "dom", status, text, CONVERSATION, MESSAGE, PARENT, "verified-observer",
    )


def test_tool_only_capture_persists_verified_identity_for_recovery(tmp_path: Path) -> None:
    store = _accepted(tmp_path)
    tool_only = CaptureResult(
        "dom", "unknown", "", CONVERSATION, MESSAGE, PARENT, "verified-observer",
        tool_calls=({"id": "tool-1", "connector": "", "action": "Search", "status": "observed"},),
    )
    assert store.write("manual-1", "123:owner", tool_only, now=12)
    row = store.get("manual-1")
    assert row is not None
    assert row["conversation_id"] == CONVERSATION
    assert row["message_id"] == MESSAGE
    assert row["parent_id"] == PARENT
    assert row["status"] == "accepted"
    assert store.finish("manual-1", "123:owner", "interrupted", now=14)
    candidate = store.next_history_recovery(now=15)
    assert candidate is not None and candidate["send_id"] == "manual-1"


def test_shorter_final_frame_does_not_erase_live_partial(tmp_path: Path) -> None:
    store = _accepted(tmp_path)
    longer = "This response was captured over several streaming frames."
    assert store.write("manual-1", "123:owner", _capture("partial", longer), now=12)
    assert store.write("manual-1", "123:owner", _capture("complete", "Done."), now=13)
    row = store.get("manual-1")
    assert row is not None
    assert row["status"] == "completed"
    assert row["assistant_text"] == longer
    assert row["message_id"] == MESSAGE


def test_shorter_historical_final_preserves_interrupted_answer(tmp_path: Path) -> None:
    store = _accepted(tmp_path)
    longer = "An already captured, meaningful partial response."
    assert store.write("manual-1", "123:owner", _capture("partial", longer), now=12)
    assert store.finish("manual-1", "123:owner", "interrupted", now=13)
    assert not store.recover_historical_response("manual-1", _capture("complete", "Done."), now=14)
    row = store.get("manual-1")
    assert row is not None
    assert row["status"] == "interrupted"
    assert row["assistant_text"] == longer
    with_tools = CaptureResult(
        "dom", "complete", "Done.", CONVERSATION, MESSAGE, PARENT, "verified-observer",
        tool_calls=({"id": "tool-1", "action": "Used search", "status": "observed"},),
    )
    assert store.recover_historical_response("manual-1", with_tools, now=15)
    saved = store.detail("manual-1")
    assert saved is not None and saved["status"] == "interrupted"
    assert saved["assistant_text"] == longer
    tool_calls = saved["tool_calls"]
    assert isinstance(tool_calls, list) and len(tool_calls) == 1
    assert store.recover_historical_response("manual-1", _capture("complete", longer), now=16)
    row = store.get("manual-1")
    assert row is not None and row["status"] == "completed"


def test_tool_only_capture_cannot_cross_a_verified_branch(tmp_path: Path) -> None:
    store = _accepted(tmp_path)
    assert store.write("manual-1", "123:owner", _capture("partial", "Partial"), now=12)
    wrong = CaptureResult(
        "dom", "unknown", "", "45678901-1234-4123-8123-123456789abc",
        MESSAGE, PARENT, "verified-observer",
        tool_calls=({"id": "tool-2", "connector": "", "action": "Other", "status": "observed"},),
    )
    assert not store.write("manual-1", "123:owner", wrong, now=13)
    row = store.get("manual-1")
    assert row is not None and row["conversation_id"] == CONVERSATION
