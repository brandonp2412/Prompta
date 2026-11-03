"""End-to-end original capture UI transitions without resending a prompt."""

from __future__ import annotations

import time
from pathlib import Path

from sqlalchemy import update

from prompta.history_recovery import HistoryRecovery
from prompta.response_capture import CaptureResult
from prompta.response_store import ResponseStore
from prompta.response_tables import results
from prompta.scheduler_runtime import SchedulerRuntime


class _UnusedDriver:
    context = "unused"

    async def connect(self) -> None:
        raise AssertionError("The test must only read a verified historical result")

    async def navigate(self, url: str, *, context: str | None = None) -> None:
        raise AssertionError("The test must not navigate")

    async def dom_state(self) -> dict[str, object]:
        raise AssertionError("The test must not scrape another tab")

    async def eval(self, expression: str) -> object:
        raise AssertionError("The test must not evaluate an unscheduled browser")

    async def close(self) -> None:
        return None


CONVERSATION = "12345678-1234-4123-8123-123456789abc"
OLDER = "12345678-1234-4123-8123-123456789abd"


def _interrupt(store: ResponseStore, send_id: str, conversation: str, stamp: float) -> None:
    store.ensure_queued(send_id, "Original prompt", now=stamp)
    assert store.accept(send_id, "123:owner", deadline=stamp + 50, now=stamp + 1)
    assert store.bind_conversation_route(
        send_id, "123:owner", "/c/" + conversation, now=stamp + 2,
    )
    assert store.finish(send_id, "123:owner", "interrupted", now=stamp + 3)


def test_newest_pinned_interruption_becomes_live_then_completed_without_resend(
    tmp_path: Path,
    monkeypatch,
) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _interrupt(store, "older-unpinned", OLDER, 10)
    _interrupt(store, "newer-pinned", CONVERSATION, 20)
    assert store.set_local_pin("newer-pinned", pinned=True)
    runtime = SchedulerRuntime(tmp_path / "runtime.sqlite3", tmp_path / "jobs.json")
    recovery = HistoryRecovery(store, runtime, _UnusedDriver, approval_enabled=False)
    calls: list[str] = []

    async def read(conversation: str, prompt: str) -> CaptureResult:
        assert conversation == CONVERSATION and prompt == "Original prompt"
        calls.append(conversation)
        if len(calls) == 1:
            return CaptureResult(
                "dom", "unknown", "", conversation, None, None,
                observer_id="fallback-turn-0:1:assistant", verified_generating=True,
            )
        return CaptureResult(
            "dom", "complete", "Verified recovered answer", conversation, None, None,
            observer_id="fallback-turn-0:1:assistant",
        )

    monkeypatch.setattr(recovery, "_read_original_response", read)
    now = time.time()
    assert not recovery.recover_once(now=now)
    underlying = store.get("newer-pinned")
    assert underlying is not None and underlying["status"] == "interrupted"
    visible = store.page()["items"]
    assert visible[0]["send_id"] == "newer-pinned"
    assert visible[0]["status"] == "generating"
    detail = store.detail("newer-pinned")
    assert detail is not None and detail["status"] == "generating"
    assert store.page(status="needs_attention")["total"] == 1  # older unpinned

    # A verified observation expires; it never papers over a truly stuck capture.
    with store.engine.begin() as connection:
        connection.execute(update(results).where(
            results.c.send_id == "newer-pinned",
        ).values(live_observed_at=now - 901))
    assert store.page()["items"][0]["status"] == "interrupted"
    assert store.page(status="needs_attention")["total"] == 2

    # The very next global recovery slot can complete the exact interrupted turn.
    assert recovery.recover_once(now=now + 301)
    saved = store.get("newer-pinned")
    assert saved is not None and saved["status"] == "completed"
    assert saved["assistant_text"] == "Verified recovered answer"
    assert store.page()["items"][0]["status"] == "completed"
    assert store.page(status="needs_attention")["total"] == 1
    assert calls == [CONVERSATION, CONVERSATION]


def test_live_observation_refuses_other_conversations(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "chat-results.sqlite3")
    _interrupt(store, "interrupted", CONVERSATION, 10)
    assert not store.observe_history_generating("interrupted", OLDER, now=time.time())
    assert store.page()["items"][0]["status"] == "interrupted"
