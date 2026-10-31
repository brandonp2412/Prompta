"""Exact-chat tool recovery cannot rewrite an answer or cross a stored branch."""

from dataclasses import replace
from pathlib import Path

import pytest

from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore
from prompta.tool_recovery import recover_completed_tool_summaries


def completed_store(tmp_path: Path) -> ResponseStore:
    store = ResponseStore(tmp_path / "results.sqlite3")
    store.ensure_queued("run", "Original prompt", now=1)
    assert store.accept("run", "100:owner", deadline=100, now=2)
    assert store.write("run", "100:owner", CaptureResult(
        "sse", "complete", "Original answer", "chat", "answer", "parent",
    ), now=3)
    return store


def recovered_capture() -> CaptureResult:
    return CaptureResult(
        "dom", "complete", "Different rendered formatting", "chat", "answer", None,
        tool_calls=({"id": "dom-tool-0", "action": "Used Calendar", "status": "observed"},),
    )


def test_completed_recovery_only_updates_tool_metadata(tmp_path: Path) -> None:
    store = completed_store(tmp_path)
    before = store.detail("run")
    assert before is not None
    before_row = store.get("run")
    assert before_row is not None
    capture = recovered_capture()
    assert recover_completed_tool_summaries(store, "run", capture, now=10)
    after = store.detail("run")
    assert after is not None
    after_row = store.get("run")
    assert after_row is not None
    assert after["tool_calls"] == list(capture.tool_calls)
    for field in ("assistant_text", "status", "source", "conversation_id", "message_id", "finished_at"):
        assert after_row[field] == before_row[field]
    assert recover_completed_tool_summaries(store, "run", capture, now=11)
    unchanged = store.detail("run")
    assert unchanged is not None and unchanged["updated_at"] == 10


@pytest.mark.parametrize("capture", [
    replace(recovered_capture(), conversation_id="other"),
    replace(recovered_capture(), message_id="other"),
    replace(recovered_capture(), message_id=None),
    replace(recovered_capture(), source="sse"),
    replace(recovered_capture(), status="partial"),
    replace(recovered_capture(), tool_calls=()),
])
def test_recovery_rejects_unverified_branch_evidence(tmp_path: Path, capture: CaptureResult) -> None:
    store = completed_store(tmp_path)
    before = store.detail("run")
    assert not recover_completed_tool_summaries(store, "run", capture, now=10)
    assert store.detail("run") == before


def test_recovery_cannot_write_to_an_active_capture(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "results.sqlite3")
    store.ensure_queued("run", "Original prompt", now=1)
    assert store.accept("run", "100:owner", deadline=100, now=2)
    assert not recover_completed_tool_summaries(store, "run", recovered_capture(), now=3)
