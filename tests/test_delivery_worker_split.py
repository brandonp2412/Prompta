from __future__ import annotations

import threading
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from prompta.cache import ActiveConversation, ChatCache
from prompta.control_server import ControlDeferredError
from prompta.conversation_actions import ConversationActions
from prompta.delivery_browser import BrowserDeliverySender
from prompta.delivery_queue import DeliveryQueueStore
from prompta.rate_limit import RateLimitError
from prompta.send_jobs import DeliveryBackendUnavailableError, SendJobRegistry


def test_delivery_worker_has_no_monolith_control_send_path() -> None:
    source = Path("src/delivery_worker.py").read_text()

    assert "_send_once_via_control" not in source
    assert "_send_reply_via_control" not in source
    assert "_daemon_is_running" not in source


def test_delivery_worker_uses_separate_browser_ownership_scope(tmp_path: Path) -> None:
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3")
    driver = sender._new_driver()

    assert driver.ownership_prefix == "prompta-delivery:"


def test_delivery_worker_sends_directly_through_browser_sender(tmp_path: Path) -> None:
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3")
    with patch.object(
        sender,
        "_send_browser",
        AsyncMock(return_value="chat-browser"),
    ) as browser_send:
        result = sender("once", "Hello", "", [])

    assert result == "chat-browser"
    browser_send.assert_awaited_once_with("once", "Hello", "", [])


@pytest.mark.asyncio
async def test_delivery_success_releases_page_but_keeps_durable_active_handoff(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "chats.sqlite3"
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        cache_path=cache_path,
    )

    async def fake_send_once(
        actions: ConversationActions,
        prompt: str,
        *,
        job_name: str = "",
        attachments: list[str] | None = None,
    ) -> str:
        del attachments
        conversation_id = "chat-handoff"
        context_id = "prompta-delivery:send-tab"
        actions.cache.start(
            conversation_id,
            context_id=context_id,
            job_name=job_name,
            prompt=prompt,
        )
        actions.active[context_id] = ActiveConversation(
            conversation_id=conversation_id,
            context_id=context_id,
            job_name=job_name,
            prompt=prompt,
        )
        return conversation_id

    with patch.object(ConversationActions, "send_once", fake_send_once):
        assert await sender._send_browser("once", "handoff", "", []) == "chat-handoff"

    cache = ChatCache(cache_path)
    try:
        row = cache.connection.execute(
            "SELECT status, browser_context_id FROM conversations WHERE id = ?",
            ("chat-handoff",),
        ).fetchone()
        assert row is not None
        assert row["status"] == "active"
        assert row["browser_context_id"] == ""
    finally:
        cache.close()


@pytest.mark.asyncio
async def test_pre_send_browser_failure_remains_retryable(tmp_path: Path) -> None:
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3")
    driver = SimpleNamespace(
        new_tab=AsyncMock(return_value="tab-1"),
        dismiss_history_rate_limit=AsyncMock(return_value=False),
        wait_for_composer=AsyncMock(side_effect=RuntimeError("browser temporarily unavailable")),
        close_context=AsyncMock(),
    )

    with patch(
        "prompta.delivery_browser.BrowserSession.ensure_driver", AsyncMock(return_value=driver)
    ):
        with pytest.raises(DeliveryBackendUnavailableError, match="temporarily unavailable"):
            await sender._send_browser("once", "Hello", "", [])


def test_delivery_worker_persists_account_rate_limit_across_restart(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime.sqlite3"
    sender = BrowserDeliverySender(state_path)
    with patch.object(
        sender,
        "_send_browser",
        AsyncMock(side_effect=RateLimitError("Too many requests", retry_after=7)),
    ):
        with pytest.raises(RateLimitError, match="Too many requests"):
            sender("once", "Hello", "", [])

    restarted = BrowserDeliverySender(state_path)
    with patch.object(
        restarted, "_send_browser", AsyncMock(return_value="should-not-send")
    ) as send:
        with pytest.raises(RateLimitError, match="backoff is active"):
            restarted("once", "Second", "", [])
    send.assert_not_awaited()


def test_delivery_worker_respects_persisted_global_send_gap(tmp_path: Path) -> None:
    state_path = tmp_path / "runtime.sqlite3"
    sender = BrowserDeliverySender(state_path)
    sender.runtime.update_scheduler_state({"last_attempt_at": time.time()})

    with patch.object(sender, "_send_browser", AsyncMock(return_value="should-not-send")) as send:
        with pytest.raises(ControlDeferredError, match="global send gap"):
            sender("once", "Second", "", [])
    send.assert_not_awaited()


def test_delivery_worker_defers_reply_when_cache_says_conversation_is_active(
    tmp_path: Path,
) -> None:
    cache_path = tmp_path / "chats.sqlite3"
    cache = ChatCache(cache_path)
    try:
        cache.start("chat-active", context_id="old-tab", job_name="", prompt="first")
    finally:
        cache.close()

    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", cache_path=cache_path)
    with patch.object(sender, "_send_browser", AsyncMock(return_value="should-not-send")) as send:
        with pytest.raises(ControlDeferredError, match="still active"):
            sender("reply", "Follow up", "chat-active", [])
    send.assert_not_awaited()


@pytest.mark.asyncio
async def test_history_rate_limit_modal_defers_before_chat_preference_checks(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    driver = SimpleNamespace(
        new_tab=AsyncMock(return_value="tab-1"),
        dismiss_history_rate_limit=AsyncMock(return_value=True),
        close_context=AsyncMock(),
    )
    ensure_high_effort = AsyncMock()
    actions = ConversationActions(
        cache,
        {},
        20.0,
        ensure_driver=AsyncMock(return_value=driver),
        ensure_high_effort=ensure_high_effort,
        ensure_route=AsyncMock(),
        enrich_completed_tool_calls=AsyncMock(),
        wait_for_cached_response=AsyncMock(return_value=False),
        unattended_mode=lambda: False,
    )
    try:
        with pytest.raises(RateLimitError, match="Too many requests"):
            await actions.send_once("Hello")
    finally:
        cache.close()

    driver.dismiss_history_rate_limit.assert_awaited_once()
    ensure_high_effort.assert_not_awaited()


def _wait_for(predicate, timeout: float = 3.0) -> bool:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if predicate():
            return True
        time.sleep(0.02)
    return predicate()


def test_producer_only_registry_observes_external_completion(tmp_path: Path) -> None:
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    producer = SendJobRegistry(None, queue_path=queue_path, consume=False)
    try:
        submitted = producer.submit(
            operation="once",
            message="hello",
            client_id="client-1",
        )
        assert producer._worker is None

        queue = DeliveryQueueStore(queue_path)
        claimed = queue.claim_next("external-worker", lease_seconds=30.0)
        assert claimed is not None
        assert claimed["send_id"] == submitted["send_id"]
        assert queue.complete_claim(
            submitted["send_id"],
            "external-worker",
            conversation_id="chat-1",
        )

        observed = producer.get(submitted["send_id"])
        assert observed is not None
        assert observed["status"] == "succeeded"
        assert observed["conversation_id"] == "chat-1"
    finally:
        producer.close()


def test_worker_rechecks_lease_before_external_send(tmp_path: Path) -> None:
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    delivered = threading.Event()

    def sender(
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str],
    ) -> str:
        delivered.set()
        return "should-not-send"

    consumer = SendJobRegistry(sender, queue_path=queue_path, consume=True)
    producer = SendJobRegistry(None, queue_path=queue_path, consume=False)
    assert consumer._delivery_queue is not None
    try:
        with patch.object(consumer._delivery_queue, "renew_lease", return_value=False):
            producer.submit(
                operation="once",
                message="cancelled ownership",
                client_id="lease-check",
            )
            assert not delivered.wait(timeout=1.2)
    finally:
        producer.close()
        consumer.close()


def test_consumer_started_before_enqueue_claims_later_sqlite_work(tmp_path: Path) -> None:
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    delivered = threading.Event()
    calls: list[tuple[str, str, str, list[str]]] = []

    def sender(
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str],
    ) -> str:
        calls.append((operation, message, conversation_id, attachments))
        delivered.set()
        return "chat-created"

    consumer = SendJobRegistry(sender, queue_path=queue_path, consume=True)
    producer = SendJobRegistry(None, queue_path=queue_path, consume=False)
    try:
        submitted = producer.submit(
            operation="once",
            message="from another process",
            client_id="client-later",
        )

        assert delivered.wait(timeout=3.0)
        assert _wait_for(
            lambda: (producer.get(submitted["send_id"]) or {}).get("status") == "succeeded"
        )
        observed = producer.get(submitted["send_id"])
        assert observed is not None
        assert observed["conversation_id"] == "chat-created"
        assert calls == [("once", "from another process", "", [])]
        assert len(DeliveryQueueStore(queue_path).records()) == 1
    finally:
        producer.close()
        consumer.close()
