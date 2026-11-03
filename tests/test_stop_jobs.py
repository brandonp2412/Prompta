"""Stopping cancels durable work and never lets capture owners revive it."""

from pathlib import Path

import pytest
from sqlalchemy import update

from prompta import stop_jobs
from prompta.reply_contracts import ReplyConflict, ReplyIntent
from prompta.reply_tables import replies
from prompta.response_capture import CaptureResult
from prompta.stop_jobs import StopJobService


def test_stop_queued_job_prevents_dispatch_and_is_idempotent(tmp_path: Path) -> None:
    service = StopJobService(tmp_path / "runtime.sqlite3")
    queued = service.queue.enqueue_manual("Do some work", request_id="a" * 32)
    send_id = str(queued["send_id"])
    assert service.results.set_local_pin(send_id, pinned=True)
    outcome = service.stop(send_id)
    assert outcome == {"ok": True, "cancelled_pending": True, "browser_stopped": False}
    assert service.queue.claim_next("worker", lease_seconds=30) is None
    detail = service.results.get(send_id)
    assert detail is not None and detail["status"] == "stopped"
    assert service.results.local_pinned_runs() == []
    assert service.stop(send_id)["ok"] is True
    assert service.results.local_pinned_runs() == []


def test_stop_active_job_clicks_exact_chat_and_preserves_partial(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StopJobService(tmp_path / "runtime.sqlite3")
    service.results.ensure_queued("active", "Work")
    assert service.results.set_local_pin("active", pinned=True)
    assert service.results.accept("active", "owner", deadline=10**12)
    partial = CaptureResult("sse", "unknown", "Saved partial answer", "chat", "message", None)
    assert service.results.write("active", "owner", partial)
    targets: list[tuple[str, str]] = []

    async def click(conversation: str, message: str) -> bool:
        targets.append((conversation, message))
        return True

    monkeypatch.setattr(stop_jobs, "click_chatgpt_stop", click)
    assert service.stop("active")["browser_stopped"] is True
    assert targets == [("chat", "message")]
    assert not service.results.write("active", "owner", partial)
    detail = service.results.get("active")
    assert detail is not None and detail["status"] == "stopped"
    assert detail["assistant_text"] == "Saved partial answer"
    assert service.results.local_pinned_runs() == []
    assert service.results.next_history_recovery() is None


def test_failed_browser_stop_keeps_capture_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StopJobService(tmp_path / "runtime.sqlite3")
    service.results.ensure_queued("active", "Work")
    assert service.results.set_local_pin("active", pinned=True)
    assert service.results.accept("active", "owner", deadline=10**12)
    assert service.results.write("active", "owner", CaptureResult(
        "sse", "unknown", "Partial", "chat", "message", None,
    ))

    async def unavailable(conversation: str, message: str) -> bool:
        return False

    monkeypatch.setattr(stop_jobs, "click_chatgpt_stop", unavailable)
    with pytest.raises(ReplyConflict, match="not available"):
        service.stop("active")
    detail = service.results.get("active")
    assert detail is not None and detail["status"] == "generating"
    assert detail["capture_owner"] == "owner"
    assert [row["send_id"] for row in service.results.local_pinned_runs()] == ["active"]


def test_stop_queued_replies_keeps_completed_original(tmp_path: Path) -> None:
    service = StopJobService(tmp_path / "runtime.sqlite3")
    service.results.ensure_queued("run", "Work")
    assert service.results.accept("run", "owner", deadline=10**12)
    assert service.results.write("run", "owner", CaptureResult(
        "sse", "complete", "Original answer", "chat", "message", None,
    ))
    intent = ReplyIntent("reply-stop-pending-1234", "chat", "message", "Follow up")
    service.replies.prepare("run", intent)
    service.stop("run")
    reply = service.replies.get(intent.reply_id)
    assert reply is not None and reply["status"] == "cancelled"
    assert not service.replies.claim(intent.reply_id, "worker", deadline=10**12)
    original = service.results.get("run")
    assert original is not None and original["status"] == "completed"
    next_intent = ReplyIntent("reply-after-stop-12345", "chat", "message", "New follow up")
    assert service.replies.prepare("run", next_intent)["status"] == "prepared"


def test_stop_http_endpoint_cancels_queued_run(tmp_path: Path) -> None:
    from web_results_support import post_json, server

    with server(tmp_path) as (app, port):
        queued = app.queue.enqueue_manual("HTTP stop", request_id="d" * 32)
        send_id = str(queued["send_id"])
        assert app.results.set_local_pin(send_id, pinned=True)
        status, body = post_json(port, f"/api/results/{send_id}/stop", {})
        assert status == 200
        assert body["cancelled_pending"] is True
        assert body["browser_stopped"] is False
        detail = app.results.get(send_id)
        assert detail is not None and detail["status"] == "stopped"
        assert app.results.local_pinned_runs() == []


def test_stop_active_reply_preserves_original_and_partial_reply(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StopJobService(tmp_path / "runtime.sqlite3")
    service.results.ensure_queued("run", "Work")
    assert service.results.set_local_pin("run", pinned=True)
    assert service.results.accept("run", "original-owner", deadline=10**12)
    assert service.results.write("run", "original-owner", CaptureResult(
        "sse", "complete", "Original answer", "chat", "message", None,
    ))
    intent = ReplyIntent("reply-active-stop-1234", "chat", "message", "Follow up")
    service.replies.prepare("run", intent)
    assert service.replies.claim(intent.reply_id, "reply-owner", deadline=10**12)
    assert service.replies.accepted(
        intent.reply_id, "reply-owner", conversation_id="chat", parent_id="message", message_id="reply-answer",
    )
    partial = CaptureResult("sse", "unknown", "Partial reply", "chat", "reply-answer", "message")
    assert service.replies.observe(intent.reply_id, "reply-owner", partial)
    targets: list[tuple[str, str]] = []

    async def click(conversation: str, message: str) -> bool:
        targets.append((conversation, message))
        return True

    monkeypatch.setattr(stop_jobs, "click_chatgpt_stop", click)
    assert service.stop("run")["browser_stopped"] is True
    assert targets == [("chat", "reply-answer")]
    reply = service.replies.get(intent.reply_id)
    assert reply is not None and reply["status"] == "stopped"
    assert reply["assistant_text"] == "Partial reply"
    assert not service.replies.observe(intent.reply_id, "reply-owner", partial)
    original = service.results.get("run")
    assert original is not None and original["status"] == "completed"
    assert service.results.local_pinned_runs() == []


def test_stop_during_dispatch_reports_retry_without_requeuing(tmp_path: Path) -> None:
    service = StopJobService(tmp_path / "runtime.sqlite3")
    queued = service.queue.enqueue_manual("Starting", request_id="e" * 32)
    send_id = str(queued["send_id"])
    assert service.queue.claim_next("worker", lease_seconds=30) is not None
    with pytest.raises(ReplyConflict, match="still starting"):
        service.stop(send_id)
    delivery = service.queue.get(send_id)
    assert delivery is not None and delivery["status"] == "running"


def test_stop_ownerless_reply_verifies_saved_chat_and_revokes_capture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StopJobService(tmp_path / "runtime.sqlite3")
    service.results.ensure_queued("run", "Original")
    assert service.results.accept("run", "original", deadline=10**12)
    assert service.results.write("run", "original", CaptureResult(
        "sse", "complete", "Original answer", "chat", "parent", None,
    ))
    service.replies.prepare("run", ReplyIntent("reply", "chat", "parent", "Follow up"))
    assert service.replies.claim("reply", "owner", deadline=10**12)
    # Reproduce the ownerless generating receipt left by deployment recovery.
    with service.results.engine.begin() as connection:
        connection.execute(update(replies).where(replies.c.reply_id == "reply").values(
            status="generating", lease_owner="",
        ))

    async def verify(
        conversation: str, original: str, *, reply_text: str, parent_id: str,
        allow_missing_reply: bool,
    ) -> tuple[bool, bool]:
        assert (conversation, original, reply_text, parent_id) == (
            "chat", "Original", "Follow up", "parent",
        )
        assert allow_missing_reply
        return True, False

    monkeypatch.setattr(stop_jobs, "stop_saved_turn", verify)
    assert service.stop("run")["browser_stopped"] is False
    reply = service.replies.get("reply")
    assert reply is not None and reply["status"] == "stopped"
    assert not service.replies.observe("reply", "owner", CaptureResult(
        "sse", "complete", "Late answer", "chat", "answer", "parent",
    ))
    assert service.stop("run")["ok"] is True


def test_stop_interrupts_recovery_without_losing_saved_answer(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    service = StopJobService(tmp_path / "runtime.sqlite3")
    service.results.ensure_queued("run", "Original")
    assert service.results.accept("run", "original", deadline=10**12)
    assert service.results.write("run", "original", CaptureResult(
        "sse", "partial", "Saved answer", "chat", "parent", None,
    ))
    assert service.results.finish("run", "original", "interrupted")
    service.results.queue_manual_recovery("run", ["run"])

    async def stop(conversation: str, message: str) -> bool:
        assert (conversation, message) == ("chat", "parent")
        return True

    monkeypatch.setattr(stop_jobs, "click_chatgpt_stop", stop)
    assert service.stop("run")["ok"] is True
    record = service.results.get("run")
    assert record is not None and record["status"] == "stopped"
    assert record["assistant_text"] == "Saved answer"
    assert service.results.manual_recovery_pending("run") == 0
    assert service.results.next_history_recovery() is None
