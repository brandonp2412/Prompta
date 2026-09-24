from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any, cast
from unittest.mock import patch

import pytest

from prompta import conversation_worker as conversation_worker_module
from prompta.cache import ActiveConversation, ChatCache
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

    async def dismiss_history_rate_limit(self, *, context: str | None = None) -> bool:
        del context
        return False

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


class FakeRateLimitedTrackingDriver(FakeTrackingDriver):
    async def dismiss_history_rate_limit(self, *, context: str | None = None) -> bool:
        del context
        return True


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


def test_conversation_worker_deduplicates_extraction_diagnostics(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    worker = ConversationWorker(
        tmp_path / "runtime.sqlite3",
        cache_path=tmp_path / "chats.sqlite3",
    )
    active = ActiveConversation(
        conversation_id="chat-diagnostics",
        context_id="prompta-conversation:diagnostics",
        job_name="",
        prompt="Inspect extraction",
    )
    snapshot = {
        "extraction_diagnostics": {
            "message_provenance": ["dom-role"],
            "source_event_provenance": ["react-private-properties"],
            "fallback_used": True,
            "fallback_reasons": ["source-events"],
            "unreconciled_expected_content": [],
        },
        "react_fallback": {
            "attempts": [
                {
                    "used": True,
                    "reason": "source-events",
                    "error": "",
                }
            ]
        },
    }

    try:
        with caplog.at_level(logging.DEBUG, logger="prompta.conversation_tracker"):
            worker.tracker._observe_extraction_diagnostics(active, snapshot)
            worker.tracker._observe_extraction_diagnostics(active, snapshot)

        fallback_records = [
            record
            for record in caplog.records
            if "transcript extraction fallback" in record.getMessage()
        ]
        assert len(fallback_records) == 1
        assert "source-events" in fallback_records[0].getMessage()

        snapshot["extraction_diagnostics"]["unreconciled_expected_content"] = [
            "structured-tool-source-events"
        ]
        with caplog.at_level(logging.WARNING, logger="prompta.conversation_tracker"):
            worker.tracker._observe_extraction_diagnostics(active, snapshot)

        assert any(
            "unreconciled=('structured-tool-source-events',)" in record.getMessage()
            for record in caplog.records
        )
    finally:
        worker.cache.close()


@pytest.mark.asyncio
async def test_machine_gun_mode_off_reclaims_and_polls_unattended_conversation(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "runtime.sqlite3"
    cache_path = tmp_path / "chats.sqlite3"
    conversation_id = "chat-machine-gun-transition"

    cache = ChatCache(cache_path)
    cache.start(
        conversation_id,
        context_id="prompta-delivery:send-tab",
        job_name="machine-gun-transition",
        prompt="Keep working after Machine Gun Mode is disabled",
    )
    assert cache.release_browser_context(
        conversation_id,
        context_id="prompta-delivery:send-tab",
    )
    cache.close()

    driver = FakeTrackingDriver("prompta-conversation:recovered", conversation_id)
    driver_factory_calls = 0

    def driver_factory() -> FakeTrackingDriver:
        nonlocal driver_factory_calls
        driver_factory_calls += 1
        return driver

    worker = ConversationWorker(
        state_path,
        cache_path=cache_path,
        driver_factory=cast(Any, driver_factory),
        recovery_message_timeout_seconds=0.01,
    )
    try:
        worker.runtime.set_unattended_mode(True)
        assert await worker.run_once() is True
        assert worker.cache.status(conversation_id) == "unattended"
        assert driver_factory_calls == 0
        assert worker.tracker.active == {}

        worker.runtime.set_unattended_mode(False)
        with patch.object(
            driver,
            "conversation_activity",
            wraps=driver.conversation_activity,
        ) as activity:
            assert await worker.run_once() is True
            activity.assert_awaited()

        assert driver_factory_calls == 1
        assert worker.cache.status(conversation_id) == "active"
        assert list(worker.tracker.active) == ["prompta-conversation:recovered"]
        assert _browser_context_id(worker.cache, conversation_id) == (
            "prompta-conversation:recovered"
        )
    finally:
        await worker.close()


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


@pytest.mark.asyncio
async def test_conversation_worker_keeps_watchdog_alive_during_long_async_poll(
    tmp_path: Path,
) -> None:
    worker = ConversationWorker(
        tmp_path / "runtime.sqlite3",
        cache_path=tmp_path / "chats.sqlite3",
    )

    async def slow_poll() -> bool:
        await asyncio.sleep(0.04)
        raise RuntimeError("stop after heartbeat")

    try:
        with (
            patch.object(worker, "run_once", new=slow_poll),
            patch.object(conversation_worker_module, "_WATCHDOG_HEARTBEAT_SECONDS", 0.01),
            patch.object(conversation_worker_module, "notify_watchdog") as notify,
            patch.object(
                conversation_worker_module.ServiceHealthStore,
                "beat",
                autospec=True,
                return_value=True,
            ) as beat,
            pytest.raises(RuntimeError, match="stop after heartbeat"),
        ):
            await worker.run_forever()

        assert notify.call_count >= 3
        assert beat.call_count >= 2
        assert all(call.args[1] == "conversation_worker" for call in beat.call_args_list)
    finally:
        await worker.close()


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


@pytest.mark.asyncio
async def test_conversation_worker_dismisses_modal_without_shared_send_cooldown(
    tmp_path: Path,
) -> None:
    state_path = tmp_path / "runtime.sqlite3"
    driver = FakeRateLimitedTrackingDriver("prompta-conversation:modal", "chat-modal")
    worker = ConversationWorker(
        state_path,
        cache_path=tmp_path / "chats.sqlite3",
        driver_factory=cast(Any, lambda: driver),
    )
    try:
        assert await worker.run_once() is False
        status = worker.runtime.account_admission_status()
        assert status["blocked"] is False
        assert status["kind"] == ""
    finally:
        await worker.close()
