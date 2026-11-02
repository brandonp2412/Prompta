"""Fault-injected HTTP 500 acceptance evidence and crash-safe local receipts."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from _browser_fakes import FakeDriver

import prompta.delivery_browser as delivery_browser
from prompta.delivery_browser import BrowserDeliverySender
from prompta.delivery_queue import DeliveryQueueStore
from prompta.response_capture import CaptureResult
from prompta.send_outcome import SendOutcomeUnknownError

CHAT = "10101010-1010-4010-8010-101010101010"
OTHER_CHAT = "20202020-2020-4020-8020-202020202020"
ASSISTANT = "30303030-3030-4030-8030-303030303030"
LOCAL_CHAT = "/c/local-chatgpt%3A25dba182-78b4-4e27-996b-d63d8f05089d"


class Http500Driver(FakeDriver):
    def __init__(self, *, accepted: bool, mismatch: bool = False) -> None:
        super().__init__()
        self.capture["status"] = 500
        self.clicks = 0
        self.accepted = accepted
        self.mismatch = mismatch
        self.route = "/"
        self.emitted = False

    async def eval(self, _script: str, *, main_world: bool = False) -> str:
        return self.route

    async def click_send(self, expected_message: str) -> None:
        self.clicks += 1
        await super().click_send(expected_message)
        if self.accepted:
            self.route = "/c/" + CHAT

    def captured_send_response(self, _capture: dict[str, object]) -> None:
        return None

    async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
        if self.accepted and not self.emitted:
            self.emitted = True
            return CaptureResult(
                "dom", "complete", "Synthetic assistant answer",
                OTHER_CHAT if self.mismatch else CHAT,
                ASSISTANT, None, "fallback-turn-0:0:assistant",
            )
        await asyncio.sleep(min(timeout, 0.01))
        return None


@pytest.mark.asyncio
async def test_provisional_chat_generation_cannot_confirm_eventual_http500(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A local optimistic chat and Stop control can precede HTTP 500."""
    class ProvisionalFailureDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.sent = False
            self.clicks = 0
            self.probes = 0

        async def eval(self, _script: str, *, main_world: bool = False) -> str:
            return LOCAL_CHAT if self.sent else "/"

        async def click_send(self, expected_message: str) -> None:
            await super().click_send(expected_message)
            self.sent = True
            self.clicks += 1
            self.composer = ""

        async def send_confirmation_state(self) -> dict[str, object]:
            self.probes += 1
            if self.probes >= 2:
                self.capture["status"] = 500
            return {"composer_text": "", "send_in_progress": True}

        def captured_send_response(self, _capture: dict[str, object]) -> None:
            return None

    monkeypatch.setattr(delivery_browser, "_SEND_CONFIRM_POLL_SECONDS", 0.001)
    driver = ProvisionalFailureDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3", driver_factory=lambda: driver,
        send_timeout_seconds=1,
    )
    with pytest.raises(SendOutcomeUnknownError) as caught:
        await sender._send_browser("Synthetic scheduled request")
    assert caught.value.stage == "send_response"
    assert "provisional_chat=True" in str(caught.value)
    assert "persistent_chat=False" in str(caught.value)
    assert driver.probes >= 2
    assert driver.clicks == 1
    assert driver.closed_contexts == ["fresh-tab"]


@pytest.mark.asyncio
async def test_provisional_chat_can_be_confirmed_after_persistent_route(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A real server route may replace the optimistic local route."""
    class LaterPersistentDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.sent = False
            self.path = "/"
            self.probes = 0
            self.clicks = 0

        async def eval(self, _script: str, *, main_world: bool = False) -> str:
            return self.path

        async def click_send(self, expected_message: str) -> None:
            await super().click_send(expected_message)
            self.sent = True
            self.clicks += 1
            self.composer = ""
            self.path = LOCAL_CHAT

        async def send_confirmation_state(self) -> dict[str, object]:
            self.probes += 1
            if self.probes >= 2:
                self.path = "/c/" + CHAT
            return {"composer_text": "", "send_in_progress": True}

        def captured_send_response(self, _capture: dict[str, object]) -> None:
            return None

    monkeypatch.setattr(delivery_browser, "_SEND_CONFIRM_POLL_SECONDS", 0.001)
    driver = LaterPersistentDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3", driver_factory=lambda: driver,
        send_timeout_seconds=1,
    )
    await sender._send_browser("Synthetic scheduled request")
    assert driver.probes >= 2
    assert driver.clicks == 1
    assert driver.closed_contexts == ["fresh-tab"]


def queue_send(queue: DeliveryQueueStore, request_id: str) -> str:
    receipt = queue.enqueue_manual(
        "Synthetic scheduled request", request_id=request_id, now=time.time()
    )
    send_id = str(receipt["send_id"])
    claimed = queue.claim_next("worker", lease_seconds=300)
    assert claimed is not None and claimed["send_id"] == send_id
    return send_id


@pytest.mark.asyncio
async def test_http500_after_acceptance_survives_restart_without_duplicate_send(
    tmp_path: Path,
) -> None:
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    send_id = queue_send(queue, "a" * 32)
    driver = Http500Driver(accepted=True)
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3", driver_factory=lambda: driver,
        send_timeout_seconds=1,
    )
    await sender._send_browser("Synthetic scheduled request", send_id=send_id)

    persisted = queue.results.get(send_id)
    assert persisted is not None
    assert persisted["status"] == "completed"
    assert isinstance(persisted["accepted_at"], (int, float))
    assert persisted["accepted_at"] > 0
    assert persisted["conversation_id"] == CHAT
    assert persisted["message_id"] == ASSISTANT
    assert persisted["source"] == "dom"
    assert driver.clicks == 1
    assert driver.closed_contexts == ["fresh-tab"]

    # Simulate a crash/lost queue acknowledgment after the durable tab receipt.
    assert queue.fail_claim(
        send_id, "worker", status="outcome_unknown", error="HTTP 500 after dispatch"
    )
    restarted = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    assert restarted.reconcile_accepted_outcomes() == 1
    assert restarted.reconcile_accepted_outcomes() == 0
    receipt = restarted.get(send_id)
    assert receipt is not None and receipt["status"] == "succeeded"
    assert restarted.claim_next("new-worker", lease_seconds=30) is None
    assert driver.clicks == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("accepted", "mismatch"), [(False, False), (True, True)],
    ids=["500-before-acceptance", "500-with-foreign-branch"],
)
async def test_http500_without_exact_owned_acceptance_remains_quarantined(
    tmp_path: Path, accepted: bool, mismatch: bool,
) -> None:
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    send_id = queue_send(queue, "b" * 32)
    driver = Http500Driver(accepted=accepted, mismatch=mismatch)
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3", driver_factory=lambda: driver,
        send_timeout_seconds=1,
    )
    with pytest.raises(SendOutcomeUnknownError) as caught:
        await sender._send_browser("Synthetic scheduled request", send_id=send_id)
    assert caught.value.stage == "send_response"
    assert driver.clicks == 1

    assert queue.fail_claim(
        send_id, "worker", status="outcome_unknown", error="HTTP 500 after dispatch"
    )
    restarted = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    assert restarted.reconcile_accepted_outcomes() == 0
    receipt = restarted.get(send_id)
    result = restarted.results.get(send_id)
    assert receipt is not None and receipt["status"] == "outcome_unknown"
    assert result is not None and result["status"] == "outcome_unknown"
    assert result["accepted_at"] == 0
    assert result["conversation_id"] == ""
    assert restarted.claim_next("new-worker", lease_seconds=30) is None
    assert driver.clicks == 1
    assert restarted.results.page(status="needs_attention")["total"] == 1


def test_observed_acceptance_cannot_overwrite_immutable_result(tmp_path: Path) -> None:
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    send_id = queue_send(queue, "c" * 32)
    capture = CaptureResult(
        "dom", "complete", "Synthetic assistant answer", CHAT,
        ASSISTANT, None, "fallback-turn-0:0:assistant",
    )
    assert queue.results.accept_observed(
        send_id, "worker", capture, deadline=time.time() + 100
    )
    assert not queue.results.accept_observed(
        send_id, "other-worker", capture, deadline=time.time() + 100
    )
    original = queue.results.get(send_id)
    assert original is not None and original["message_id"] == ASSISTANT


@pytest.mark.asyncio
async def test_late_owned_tab_proof_reconciles_previously_uncertain_receipt(
    tmp_path: Path,
) -> None:
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    send_id = queue_send(queue, "d" * 32)
    assert queue.fail_claim(
        send_id, "worker", status="outcome_unknown", error="Handoff lost after dispatch"
    )
    uncertain = queue.results.get(send_id)
    assert uncertain is not None and uncertain["status"] == "outcome_unknown"

    # The original dispatch thread survives the queue handoff loss and
    # subsequently observes its own accepted assistant turn.
    driver = Http500Driver(accepted=True)
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3", driver_factory=lambda: driver,
        send_timeout_seconds=1,
    )
    await sender._send_browser("Synthetic scheduled request", send_id=send_id)
    saved = queue.results.get(send_id)
    assert saved is not None
    assert isinstance(saved["accepted_at"], (int, float))
    assert saved["accepted_at"] > 0
    assert saved["conversation_id"] == CHAT
    assert saved["message_id"] == ASSISTANT

    restarted = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    assert restarted.reconcile_accepted_outcomes() == 1
    reconciled = restarted.get(send_id)
    assert reconciled is not None and reconciled["status"] == "succeeded"
    assert restarted.claim_next("other-worker", lease_seconds=30) is None
    assert driver.clicks == 1


def test_legacy_ambiguous_receipt_projects_clear_local_status_without_resend(
    tmp_path: Path,
) -> None:
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    send_id = queue_send(queue, "e" * 32)
    assert queue.fail_claim(
        send_id, "worker", status="outcome_unknown", error="HTTP 500 after dispatch"
    )

    # Historical releases projected uncertainty as an unavailable transcript.
    with queue.results.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE job_responses SET status='unavailable' WHERE send_id=?",
            (send_id,),
        )
    restarted = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    assert restarted.reconcile_accepted_outcomes() == 0
    saved = restarted.results.get(send_id)
    assert saved is not None and saved["status"] == "outcome_unknown"
    assert saved["accepted_at"] == 0
    quarantined = restarted.get(send_id)
    assert quarantined is not None and quarantined["status"] == "outcome_unknown"
    assert restarted.claim_next("another-worker", lease_seconds=30) is None


@pytest.mark.asyncio
async def test_http500_rate_limit_banner_never_authorizes_retry(tmp_path: Path) -> None:
    class BannerDriver(Http500Driver):
        async def send_confirmation_state(self) -> dict[str, object]:
            return {
                "composer_text": self.composer,
                "send_in_progress": False,
                "rate_limit_text": "Too many requests. Try again later.",
            }

    driver = BannerDriver(accepted=False)
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3", driver_factory=lambda: driver,
        send_timeout_seconds=1,
    )
    with pytest.raises(SendOutcomeUnknownError) as caught:
        await sender._send_browser("Synthetic scheduled request")
    assert caught.value.stage == "send_response"
    assert driver.clicks == 1


def test_verified_historical_branch_is_not_downgraded_to_unknown(
    tmp_path: Path,
) -> None:
    queue = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    send_id = queue_send(queue, "f" * 32)
    assert queue.fail_claim(
        send_id, "worker", status="outcome_unknown", error="HTTP 500 after dispatch"
    )
    with queue.results.engine.begin() as connection:
        connection.exec_driver_sql(
            "UPDATE job_responses SET status='unavailable', conversation_id=? WHERE send_id=?",
            (CHAT, send_id),
        )
    restarted = DeliveryQueueStore(tmp_path / "ui-send-jobs.sqlite3")
    assert restarted.reconcile_accepted_outcomes() == 0
    preserved = restarted.results.get(send_id)
    assert preserved is not None
    assert preserved["status"] == "unavailable"
    assert preserved["conversation_id"] == CHAT
