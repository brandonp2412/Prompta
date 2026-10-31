"""Read-only recovery of later replies in an exact, saved Prompta branch."""

from __future__ import annotations

from pathlib import Path

from sqlalchemy import update

from prompta.history_recovery import HistoryRecovery
from prompta.reply_contracts import ManualReplyStore, ReplyIntent
from prompta.reply_contracts import replies as reply_table
from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore
from prompta.scheduler_runtime import SchedulerRuntime

CONVERSATION = "12345678-1234-4123-8123-123456789abc"
ORIGINAL_ID = "11111111-1111-4111-8111-111111111111"
FIRST_REPLY_ID = "22222222-2222-4222-8222-222222222222"
SECOND_REPLY_ID = "33333333-3333-4333-8333-333333333333"


def _chain(tmp_path: Path) -> tuple[ResponseStore, ManualReplyStore, str]:
    path = tmp_path / "chat-results.sqlite3"
    responses = ResponseStore(path)
    replies = ManualReplyStore(path)
    responses.ensure_queued("chain-run", "Original prompt", now=10)
    assert responses.accept("chain-run", "123:owner", deadline=200, now=11)
    assert responses.write(
        "chain-run", "123:owner",
        CaptureResult("sse", "complete", "Original answer", CONVERSATION, ORIGINAL_ID, None),
        now=12,
    )
    first = ReplyIntent("first-reply", CONVERSATION, ORIGINAL_ID, "First follow-up")
    assert replies.prepare("chain-run", first, now=13)["status"] == "prepared"
    assert replies.claim(first.reply_id, "123:reply", deadline=200, now=14)
    assert replies.accepted(
        first.reply_id, "123:reply", conversation_id=CONVERSATION,
        parent_id=ORIGINAL_ID, message_id=FIRST_REPLY_ID, now=15,
    )
    assert replies.observe(
        first.reply_id, "123:reply",
        CaptureResult("sse", "complete", "First answer", CONVERSATION,
                      FIRST_REPLY_ID, ORIGINAL_ID),
        now=16,
    )
    second = ReplyIntent("second-reply", CONVERSATION, FIRST_REPLY_ID, "Second follow-up")
    assert replies.prepare("chain-run", second, now=17)["status"] == "prepared"
    assert replies.claim(second.reply_id, "123:reply2", deadline=200, now=18)
    assert replies.finish(second.reply_id, "123:reply2", uncertain=True, now=19)
    return responses, replies, second.reply_id


def test_later_uncertain_reply_is_eligible_only_with_verified_predecessor(tmp_path: Path) -> None:
    _, replies, reply_id = _chain(tmp_path)
    candidate = replies.next_history_reply_recovery(now=20)
    assert candidate is not None
    assert candidate["reply_id"] == reply_id
    assert candidate["parent_id"] == FIRST_REPLY_ID
    assert replies.reply_recovery_metrics(now=20) == {
        "unresolved_reply_captures": 1,
        "recoverable_reply_captures": 1,
        "due_reply_recovery_probes": 1,
    }

    assert not replies.recover_historical_reply(
        reply_id, CaptureResult("dom", "complete", "Wrong parent", CONVERSATION,
                                SECOND_REPLY_ID, ORIGINAL_ID, "turn"), now=21,
    )
    assert not replies.recover_historical_reply(
        reply_id, CaptureResult("dom", "complete", "Wrong chat",
                                "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",
                                SECOND_REPLY_ID, FIRST_REPLY_ID, "turn"), now=22,
    )
    unresolved = replies.get(reply_id)
    assert unresolved is not None and unresolved["status"] == "outcome_unknown"


def test_later_reply_recovers_via_one_read_only_exact_chat_visit(tmp_path: Path) -> None:
    responses, replies, reply_id = _chain(tmp_path)

    class ReadOnlyDriver:
        context = "owned"

        def __init__(self) -> None:
            self.visited: list[str] = []
            self.closed = False

        async def connect(self) -> None:
            self.visited.append("connect")

        async def navigate(self, url: str, *, context: str | None = None) -> None:
            assert context == self.context
            self.visited.append(url)

        async def dom_state(self) -> dict[str, object]:
            return {}

        async def eval(self, expression: str, *, main_world: bool = False) -> object:
            assert "Second follow-up" in expression and FIRST_REPLY_ID in expression
            return {
                "verified": True, "ambiguous": False,
                "message_id": "second-unit", "branch_message_id": SECOND_REPLY_ID,
                "verified_parent_id": FIRST_REPLY_ID,
                "pathname": "/c/" + CONVERSATION, "text": "Recovered second answer",
                "complete": True,
            }

        async def close(self) -> None:
            self.closed = True

    driver = ReadOnlyDriver()
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert HistoryRecovery(responses, runtime, lambda: driver).recover_once(now=20)
    assert driver.visited == ["connect", "https://chatgpt.com/c/" + CONVERSATION]
    assert driver.closed
    recovered = replies.get(reply_id)
    assert recovered is not None and recovered["status"] == "completed"
    assert recovered["assistant_text"] == "Recovered second answer"
    assert recovered["message_id"] == SECOND_REPLY_ID
    assert replies.next_history_reply_recovery(now=1000) is None
    assert replies.reply_recovery_metrics(now=1000) == {
        "unresolved_reply_captures": 0,
        "recoverable_reply_captures": 0,
        "due_reply_recovery_probes": 0,
    }


def test_shorter_tool_snapshot_never_marks_partial_reply_complete(tmp_path: Path) -> None:
    _, replies, reply_id = _chain(tmp_path)
    # Simulate an already-persisted partial assistant answer before the capture
    # worker was interrupted, then a shorter DOM snapshot with tool metadata.
    partial = "A substantial partial answer that must survive."
    with replies.engine.begin() as connection:
        connection.execute(update(reply_table).where(
            reply_table.c.reply_id == reply_id
        ).values(status="interrupted", assistant_text=partial))

    short = CaptureResult(
        "dom", "complete", "OK", CONVERSATION, SECOND_REPLY_ID,
        FIRST_REPLY_ID, "turn", tool_calls=(
            {"id": "tool-1", "connector": "", "action": "Lookup", "status": "completed"},
        ),
    )
    assert replies.recover_historical_reply(reply_id, short, now=21)
    saved = replies.get(reply_id)
    assert saved is not None
    assert saved["assistant_text"] == partial and saved["status"] == "interrupted"
    assert replies.recover_historical_reply(
        reply_id, CaptureResult("dom", "complete", "Fully recovered complete answer with enough verified detail to replace the partial.",
                                CONVERSATION, SECOND_REPLY_ID, FIRST_REPLY_ID, "turn"),
        now=22,
    )
    completed = replies.get(reply_id)
    assert completed is not None
    assert completed["status"] == "completed"
    assert completed["assistant_text"] == "Fully recovered complete answer with enough verified detail to replace the partial."


def test_short_complete_looking_probe_remains_retryable_after_storage_guard(tmp_path: Path) -> None:
    responses, replies, reply_id = _chain(tmp_path)
    with replies.engine.begin() as connection:
        connection.execute(update(reply_table).where(
            reply_table.c.reply_id == reply_id
        ).values(status="interrupted", assistant_text="A long saved partial answer must survive."))

    class ShortReadOnlyDriver:
        context = "owned"

        async def connect(self) -> None:
            return None

        async def navigate(self, url: str, *, context: str | None = None) -> None:
            assert url == "https://chatgpt.com/c/" + CONVERSATION
            assert context == self.context

        async def dom_state(self) -> dict[str, object]:
            return {}

        async def eval(self, expression: str, *, main_world: bool = False) -> object:
            assert "Second follow-up" in expression
            return {
                "verified": True, "ambiguous": False,
                "message_id": "second-unit", "branch_message_id": SECOND_REPLY_ID,
                "verified_parent_id": FIRST_REPLY_ID,
                "pathname": "/c/" + CONVERSATION, "text": "OK",
                "complete": True,
                "tool_calls": [{"action": "Lookup", "status": "completed"}],
            }

        async def close(self) -> None:
            return None

    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    assert not HistoryRecovery(responses, runtime, ShortReadOnlyDriver).recover_once(now=21)
    still_partial = replies.get(reply_id)
    assert still_partial is not None and still_partial["status"] == "interrupted"
    assert still_partial["assistant_text"] == "A long saved partial answer must survive."
    assert replies.reply_recovery_metrics(now=22)["due_reply_recovery_probes"] == 0
