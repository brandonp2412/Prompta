from pathlib import Path

from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore

CONVERSATION = "12345678-1234-4123-8123-123456789abc"


def test_response_detail_shows_only_bounded_read_only_recovery_metadata(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "results.sqlite3")
    store.ensure_queued("run", "Private prompt", now=100)
    assert store.accept("run", "owner", deadline=150, now=101)
    assert store.write(
        "run",
        "owner",
        CaptureResult("dom", "partial", "Saved answer", CONVERSATION, "message", None),
        now=102,
    )
    assert store.finish("run", "owner", "interrupted", now=103)

    first = store.detail("run")
    assert first is not None
    assert first["recovery"] == {
        "attempt_count": 0,
        "last_attempt_at": 0,
        "next_attempt_at": 0,
        "eligible": True,
    }
    store.schedule_history_recovery("run", now=110, next_attempt_at=200)
    store.schedule_history_recovery("run", now=201, next_attempt_at=381)
    later = store.detail("run")
    assert later is not None
    assert later["recovery"] == {
        "attempt_count": 2,
        "last_attempt_at": 201,
        "next_attempt_at": 381,
        "eligible": True,
    }
    assert later["assistant_text"] == "Saved answer"
    assert "capture_owner" not in later
    assert "history_recovery_attempts" not in later


def test_queued_and_completed_details_do_not_claim_recovery(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "results.sqlite3")
    store.ensure_queued("queued", "Private prompt", now=100)
    queued = store.detail("queued")
    assert queued is not None and "recovery" not in queued
    store.ensure_queued("finished", "Private prompt", now=100)
    assert store.accept("finished", "owner", deadline=150, now=101)
    assert store.write(
        "finished",
        "owner",
        CaptureResult("dom", "complete", "Full answer", CONVERSATION, "message", None),
        now=102,
    )
    completed = store.detail("finished")
    assert completed is not None and "recovery" not in completed
