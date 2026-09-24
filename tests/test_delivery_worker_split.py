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
async def test_history_rate_limit_modal_is_dismissed_without_send_backoff() -> None:
    driver = SimpleNamespace(
        dismiss_history_rate_limit=AsyncMock(return_value=True),
    )

    await ConversationActions._raise_if_history_rate_limited(driver)

    driver.dismiss_history_rate_limit.assert_awaited_once()


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


def test_producer_observer_keeps_queue_position_and_eta_for_waiting_retry_states(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    producer = SendJobRegistry(None, queue_path=queue_path, consume=False)
    queue = DeliveryQueueStore(queue_path)
    now = time.time()
    try:
        first = producer.submit(operation="once", message="first", client_id="client-1")
        second = producer.submit(operation="once", message="second", client_id="client-2")
        third = producer.submit(operation="once", message="third", client_id="client-3")

        claimed_first = queue.claim_next("external-worker", now=now, lease_seconds=30.0)
        assert claimed_first is not None
        assert claimed_first["send_id"] == first["send_id"]
        assert queue.retry_claim(
            first["send_id"],
            "external-worker",
            retry_at=now + 120,
            retry_attempt=1,
            error="rate limited",
            status="rate_limited",
            now=now,
        )

        claimed_second = queue.claim_next("external-worker", now=now, lease_seconds=30.0)
        assert claimed_second is not None
        assert claimed_second["send_id"] == second["send_id"]
        assert queue.retry_claim(
            second["send_id"],
            "external-worker",
            retry_at=now + 30,
            retry_attempt=1,
            error="transient failure",
            status="retrying",
            now=now,
        )

        observed_first = producer.get(first["send_id"])
        observed_second = producer.get(second["send_id"])
        observed_third = producer.get(third["send_id"])

        assert observed_first is not None
        assert observed_second is not None
        assert observed_third is not None
        assert observed_first["queue_position"] == 1
        assert observed_second["queue_position"] == 2
        assert observed_third["queue_position"] == 3
        assert observed_first["queue_eta_at"] == pytest.approx(now + 120, abs=2)
        assert observed_second["queue_eta_at"] == pytest.approx(now + 420, abs=2)
        assert observed_third["queue_eta_at"] == pytest.approx(now + 720, abs=2)
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


def test_infrastructure_retry_backoff_survives_reclaim_and_worker_restart(
    tmp_path: Path,
) -> None:
    queue_path = tmp_path / "ui-send-jobs.sqlite3"
    calls = 0

    def unavailable(*_args: object) -> str:
        nonlocal calls
        calls += 1
        raise DeliveryBackendUnavailableError("browser unavailable before send")

    first = SendJobRegistry(unavailable, queue_path=queue_path)
    try:
        submitted = first.submit(operation="once", message="Please post")
        assert _wait_for(
            lambda: (first.get(submitted["send_id"]) or {}).get("infrastructure_retry_attempt") == 1
        )
        record = first.get(submitted["send_id"])
        assert record is not None
        assert record["retry_attempt"] == 0
        assert record["retry_after_seconds"] <= 2
    finally:
        first.close()

    second = SendJobRegistry(unavailable, queue_path=queue_path)
    try:
        record = second.get(submitted["send_id"])
        assert record is not None
        assert record["status"] == "retrying"
        assert record["infrastructure_retry_attempt"] == 1
        assert record["retry_at"] > time.time()
        assert calls == 1

        connection = DeliveryQueueStore(queue_path).connect()
        try:
            connection.execute(
                "UPDATE send_jobs SET retry_at = ? WHERE send_id = ?",
                (time.time() - 1, submitted["send_id"]),
            )
            connection.commit()
        finally:
            connection.close()
        second._work_event.set()
        assert _wait_for(
            lambda: (
                (second.get(submitted["send_id"]) or {}).get("infrastructure_retry_attempt") == 2
            )
        )
        record = second.get(submitted["send_id"])
        assert record is not None
        assert record["retry_at"] - time.time() > 2.5
        assert record["retry_attempt"] == 0
        assert calls == 2
    finally:
        second.close()


@pytest.mark.asyncio
async def test_pre_send_draft_deferral_keeps_its_retry_delay(tmp_path: Path) -> None:
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3")
    with (
        patch.object(
            ConversationActions,
            "send_reply",
            AsyncMock(
                side_effect=ControlDeferredError(
                    "ChatGPT composer already contains unsent text", retry_after=60
                )
            ),
        ),
        pytest.raises(ControlDeferredError) as deferred,
    ):
        await sender._send_browser("reply", "Queued reply", "chat-1", [])

    assert deferred.value.retry_after == 60
