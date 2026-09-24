from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from prompta.cache import ChatCache
from prompta.conversation_worker import ConversationWorker


class FakeTrackingDriver:
    def __init__(self, context_id: str, conversation_id: str) -> None:
        self.context_id = context_id
        self.conversation_id = conversation_id
        self.is_connected = True
        self.needs_browser_restart = False
        self.closed_contexts: list[str] = []
        self.closed = False

    async def connect(self) -> None:
        self.is_connected = True

    async def cleanup_orphan_pages(self) -> int:
        return 0

    async def new_tab(self, _url: str = "https://chatgpt.com/") -> str:
        return self.context_id

    async def eval(self, _script: str, *, context: str | None = None) -> str:
        assert context == self.context_id
        return f"/c/{self.conversation_id}"

    async def conversation_snapshot(self, context: str) -> dict[str, Any]:
        assert context == self.context_id
        return {
            "messages": [
                {"id": "u1", "role": "user", "content": "Do the work"},
                {
                    "id": "a1",
                    "role": "assistant",
                    "content": "Working",
                    "status": "streaming",
                },
            ],
            "streaming": True,
        }

    async def conversation_activity(self, context: str) -> dict[str, Any]:
        assert context == self.context_id
        return {
            "streaming": True,
            "complete": False,
            "transient": False,
            "failed": False,
            "turn_ended": None,
        }

    async def close_context(self, context: str) -> None:
        self.closed_contexts.append(context)

    async def close(self) -> None:
        self.closed = True
        self.is_connected = False


def _browser_context_id(cache: ChatCache, conversation_id: str) -> str:
    row = cache.connection.execute(
        "SELECT browser_context_id FROM conversations WHERE id = ?",
        (conversation_id,),
    ).fetchone()
    assert row is not None
    return str(row["browser_context_id"])


def test_conversation_worker_uses_separate_browser_ownership_scope(tmp_path: Path) -> None:
    worker = ConversationWorker(
        tmp_path / "runtime.sqlite3",
        cache_path=tmp_path / "chats.sqlite3",
    )
    try:
        driver = worker._new_driver()
        assert driver.ownership_prefix == "prompta-conversation:"
    finally:
        worker.cache.close()


@pytest.mark.asyncio
async def test_conversation_worker_restart_reclaims_durable_active_handoff(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "runtime.sqlite3"
    cache_path = tmp_path / "chats.sqlite3"
    conversation_id = "chat-restart"

    delivery_cache = ChatCache(cache_path)
    delivery_cache.start(
        conversation_id,
        context_id="prompta-delivery:send-tab",
        job_name="slice-five",
        prompt="Do the work",
    )
    assert delivery_cache.release_browser_context(
        conversation_id,
        context_id="prompta-delivery:send-tab",
    )
    assert delivery_cache.status(conversation_id) == "active"
    assert _browser_context_id(delivery_cache, conversation_id) == ""
    delivery_cache.close()

    first_driver = FakeTrackingDriver("prompta-conversation:first", conversation_id)
    first = ConversationWorker(
        state_path,
        cache_path=cache_path,
        driver_factory=cast(Any, lambda: first_driver),
        recovery_message_timeout_seconds=0.01,
    )
    assert await first.run_once() is True
    assert list(first.tracker.active) == ["prompta-conversation:first"]
    assert _browser_context_id(first.cache, conversation_id) == "prompta-conversation:first"
    await first.close()

    after_stop = ChatCache(cache_path)
    assert after_stop.status(conversation_id) == "active"
    assert _browser_context_id(after_stop, conversation_id) == ""
    after_stop.close()

    second_driver = FakeTrackingDriver("prompta-conversation:second", conversation_id)
    second = ConversationWorker(
        state_path,
        cache_path=cache_path,
        driver_factory=cast(Any, lambda: second_driver),
        recovery_message_timeout_seconds=0.01,
    )
    try:
        assert await second.run_once() is True
        assert list(second.tracker.active) == ["prompta-conversation:second"]
        assert _browser_context_id(second.cache, conversation_id) == ("prompta-conversation:second")
        assert second.cache.status(conversation_id) == "active"
    finally:
        await second.close()


def test_reply_busy_is_derived_from_durable_cache_not_local_tracker(tmp_path: Path) -> None:
    from prompta.core import Prompta, PromptaConfig

    prompta = Prompta(
        PromptaConfig(
            jobs_file=tmp_path / "runtime.sqlite3",
            state_path=tmp_path / "runtime.sqlite3",
            cache_path=tmp_path / "chats.sqlite3",
        ),
        "ws://unused",
    )
    try:
        prompta.cache.start(
            "chat-active",
            context_id="prompta-conversation:other-process",
            job_name="",
            prompt="Still running",
        )
        assert not prompta._active_conversations
        assert prompta._reply_target_is_busy("chat-active") is True

        prompta.cache.mark_interrupted("chat-active")
        assert prompta._reply_target_is_busy("chat-active") is False
    finally:
        prompta.cache.close()
