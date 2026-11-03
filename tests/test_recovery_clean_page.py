"""A clean exact-branch recovery read is healthy even without new assistant text."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from sqlalchemy import update

import prompta.history_recovery as recovery_module
from prompta.history_recovery import HistoryRecovery
from prompta.reply_contracts import ManualReplyStore, ReplyIntent
from prompta.reply_tables import replies as replies_table
from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore
from prompta.scheduler_runtime import SchedulerRuntime

CONVERSATION = "12345678-1234-4123-8123-123456789abc"
PARENT = "11111111-1111-4111-8111-111111111111"


class _UnusedDriver:
    context = "unused"

    async def connect(self) -> None:
        raise AssertionError("Only the exact read-only recovery path is allowed")

    async def navigate(self, url: str, *, context: str | None = None) -> None:
        raise AssertionError("No navigation is expected")

    async def dom_state(self) -> dict[str, object]:
        raise AssertionError("No DOM read is expected")

    async def eval(self, expression: str) -> object:
        raise AssertionError("No browser evaluation is expected")

    async def close(self) -> None:
        return None


def _interrupted_reply(tmp_path: Path) -> tuple[ResponseStore, ManualReplyStore, HistoryRecovery]:
    responses = ResponseStore(tmp_path / "chat-results.sqlite3")
    responses.ensure_queued("original", "Original prompt", now=10)
    assert responses.accept("original", "123:owner", deadline=100, now=11)
    assert responses.write("original", "123:owner", CaptureResult(
        "sse", "complete", "Original answer", CONVERSATION, PARENT, None,
    ), now=12)
    replies = ManualReplyStore(responses.path)
    intent = ReplyIntent("reply-id", CONVERSATION, PARENT, "Exact saved follow-up")
    replies.prepare("original", intent, now=13)
    assert replies.claim(intent.reply_id, "123:reply", deadline=100, now=14)
    assert replies.finish(intent.reply_id, "123:reply", now=15)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    worker = HistoryRecovery(responses, runtime, _UnusedDriver, approval_enabled=False)
    return responses, replies, worker


def test_clean_page_without_reply_updates_goes_green_then_stale(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    responses, replies, worker = _interrupted_reply(tmp_path)
    at = time.time()
    responses.queue_manual_recovery("original", ["reply:reply-id"], now=at - 2)

    async def clean_page(
        conversation: str, prompt: str, reply_text: str, parent: str,
    ) -> CaptureResult:
        assert (conversation, prompt, reply_text, parent) == (
            CONVERSATION, "Original prompt", "Exact saved follow-up", PARENT,
        )
        return CaptureResult(
            "dom", "unknown", "", CONVERSATION, None, PARENT,
            verified_loaded=True,
        )

    monkeypatch.setattr(worker, "_read_reply_response", clean_page)
    assert not worker.recover_once(now=at, preferred_send_id="reply:reply-id")
    observed = replies.get("reply-id")
    turns = replies.turns("original")
    assert observed is not None and observed["status"] == "generating"
    assert turns is not None and turns[-1]["status"] == "generating"
    assert responses.manual_recovery_pending("original") == 1
    with replies.engine.begin() as connection:
        connection.execute(update(replies_table).where(
            replies_table.c.reply_id == "reply-id",
        ).values(live_observed_at=at - 901))
    stale = replies.get("reply-id")
    turns = replies.turns("original")
    assert stale is not None and stale["status"] == "interrupted"
    assert turns is not None and turns[-1]["status"] == "interrupted"


def test_clean_page_does_not_green_wrong_reply_parent(tmp_path: Path) -> None:
    _, replies, worker = _interrupted_reply(tmp_path)
    assert not replies.observe_history_loaded(
        "reply-id", CONVERSATION, "22222222-2222-4222-8222-222222222222",
        now=time.time(),
    )
    assert not replies.observe_history_loaded(
        "reply-id", "22222222-2222-4222-8222-222222222222", PARENT,
        now=time.time(),
    )
    state = replies.get("reply-id")
    assert state is not None and state["status"] == "interrupted"
    assert worker is not None


def test_probe_rejects_stream_error_and_accepts_verified_empty_turn(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CleanDriver:
        context = "owned"
        stream_error = False

        async def connect(self) -> None:
            return None

        async def navigate(self, url: str, *, context: str | None = None) -> None:
            assert url == "https://chatgpt.com/c/" + CONVERSATION
            assert context == self.context

        async def dom_state(self) -> dict[str, object]:
            return {}

        async def eval(self, expression: str) -> object:
            return {
                "verified": True, "ambiguous": False, "message_id": "",
                "pathname": "/c/" + CONVERSATION, "verified_parent_id": PARENT,
                "text": "", "complete": False, "stream_error": self.stream_error,
            }

        async def close(self) -> None:
            return None

    async def no_delay(_seconds: float) -> None:
        return None

    monkeypatch.setattr(recovery_module, "_READ_PROBE_SECONDS", 0.02)
    monkeypatch.setattr(recovery_module.asyncio, "sleep", no_delay)
    responses = ResponseStore(tmp_path / "chat-results.sqlite3")
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    driver = CleanDriver()
    worker = HistoryRecovery(responses, runtime, lambda: driver, approval_enabled=False)
    result = asyncio.run(worker._read_reply_response(
        CONVERSATION, "Original prompt", "Exact saved follow-up", PARENT,
    ))
    assert result is not None and result.verified_loaded
    assert result.conversation_id == CONVERSATION and result.parent_id == PARENT
    assert result.status == "unknown" and not result.text
    driver.stream_error = True
    assert asyncio.run(worker._read_reply_response(
        CONVERSATION, "Original prompt", "Exact saved follow-up", PARENT,
    )) is None
