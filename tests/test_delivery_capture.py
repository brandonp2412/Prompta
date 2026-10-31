from __future__ import annotations

import asyncio
import threading
import time
from pathlib import Path
from unittest.mock import AsyncMock

import pytest
from _browser_fakes import FakeDriver
from _browser_fakes import offline_approval_default as offline_approval_default

import prompta.delivery_browser as delivery_browser
from prompta.delivery_browser import (
    BrowserDeliverySender,
    DeliveryBackendUnavailableError,
)
from prompta.reply_contracts import ManualReplyStore, ReplyIntent
from prompta.response_capture import CaptureResult, normalize_dom_snapshot


@pytest.mark.asyncio
async def test_connector_grace_approves_multiple_dialogs_before_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import threading

    assert delivery_browser._CONNECTOR_APPROVAL_SECONDS == 2700.0
    monkeypatch.setattr(delivery_browser, "_CONNECTOR_APPROVAL_SECONDS", 0.04)
    accepted = threading.Event()

    class PermissionDriver(FakeDriver):
        checks = 0
        approvals = 0

        async def eval(self, _script: str, *, main_world: bool = False) -> str | bool:
            if "always allow" in _script:
                assert accepted.is_set()
                assert not self.closed_contexts
                self.checks += 1
                if self.approvals < 2:
                    self.approvals += 1
                    return True
                return False
            return "/"

    driver = PermissionDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        connector_approval=True,
    )
    await sender._send_browser("Work", accepted=accepted)
    assert driver.approvals == 2
    assert driver.checks >= 3
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed


@pytest.mark.asyncio
async def test_failed_dispatch_has_no_connector_grace(tmp_path: Path) -> None:
    class RejectedDriver(FakeDriver):
        async def type_message(self, message: str) -> None:
            raise RuntimeError("not ready")

    driver = RejectedDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3", driver_factory=lambda: driver, connector_approval=True
    )
    sender._handle_connector_approvals = AsyncMock()
    with pytest.raises(DeliveryBackendUnavailableError):
        await sender._send_browser("Work")
    sender._handle_connector_approvals.assert_not_awaited()
    assert driver.closed


def test_connector_supervision_does_not_block_next_delivery(tmp_path: Path) -> None:
    import threading

    release = threading.Event()
    closed = threading.Event()
    driver = FakeDriver()

    class Sender(BrowserDeliverySender):
        async def _handle_connector_approvals(
            self, driver: delivery_browser.PassiveCaptureDriver, *, deadline: float | None = None
        ) -> None:
            await asyncio.to_thread(release.wait)

    class Driver(FakeDriver):
        async def close(self) -> None:
            await super().close()
            closed.set()

    driver = Driver()
    sender = Sender(
        tmp_path / "runtime.sqlite3", driver_factory=lambda: driver, connector_approval=True
    )
    try:
        sender("Work")
        assert not driver.closed
    finally:
        release.set()
    assert closed.wait(2)


def test_passive_capture_handoff_does_not_hold_delivery_worker(tmp_path: Path) -> None:
    class StreamedDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.ready = threading.Event()
            self.closed_event = threading.Event()
            self.clicks = 0

        async def click_send(self, expected_message: str) -> None:
            self.clicks += 1
            await super().click_send(expected_message)

        async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
            if await asyncio.to_thread(self.ready.wait, timeout):
                return CaptureResult("dom", "complete", "Done without polling", None, "m1", None)
            return None

        async def close_context(self, context: str) -> None:
            await super().close_context(context)
            self.closed_event.set()

    driver = StreamedDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        connector_approval=False,
    )
    started = time.monotonic()
    sender("Fresh chat", send_id="run-1", job_name="sample")
    assert time.monotonic() - started < 3
    assert driver.clicks == 1
    assert driver.closed_contexts == []
    accepted = sender.results.get("run-1")
    assert accepted is not None and accepted["status"] == "accepted"
    assert accepted["user_text"] == "Fresh chat"
    driver.ready.set()
    assert driver.closed_event.wait(3)
    result = sender.results.get("run-1")
    assert result is not None and result["status"] == "completed"
    assert result["assistant_text"] == "Done without polling"
    assert driver.clicks == 1


def test_multiple_passive_captures_can_overlap(tmp_path: Path) -> None:
    class PendingDriver(FakeDriver):
        def __init__(self, answer: str) -> None:
            super().__init__()
            self.answer = answer
            self.ready = threading.Event()
            self.closed_event = threading.Event()
            self.clicks = 0

        async def click_send(self, expected_message: str) -> None:
            self.clicks += 1
            await super().click_send(expected_message)

        async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
            if await asyncio.to_thread(self.ready.wait, timeout):
                return CaptureResult("dom", "complete", self.answer, None, "m1", None)
            return None

        async def close_context(self, context: str) -> None:
            await super().close_context(context)
            self.closed_event.set()

    first = PendingDriver("First answer")
    second = PendingDriver("Second answer")
    drivers = iter((first, second))
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: next(drivers),
        connector_approval=False,
    )
    try:
        sender("First job", send_id="run-1", job_name="first")
        first_accepted = sender.results.get("run-1")
        assert first_accepted is not None and first_accepted["status"] == "accepted"
        assert first.closed_contexts == []

        sender("Second job", send_id="run-2", job_name="second")
        second_accepted = sender.results.get("run-2")
        assert second_accepted is not None and second_accepted["status"] == "accepted"
        assert first.closed_contexts == []
        assert second.closed_contexts == []
        assert first.clicks == second.clicks == 1
    finally:
        first.ready.set()
        second.ready.set()

    assert first.closed_event.wait(3)
    assert second.closed_event.wait(3)
    first_result = sender.results.get("run-1")
    second_result = sender.results.get("run-2")
    assert first_result is not None and first_result["status"] == "completed"
    assert second_result is not None and second_result["status"] == "completed"
    assert first_result["assistant_text"] == "First answer"
    assert second_result["assistant_text"] == "Second answer"


@pytest.mark.asyncio
async def test_accepted_owned_chat_persists_url_and_backend_reply_identity(tmp_path: Path) -> None:
    chat = "d5c86e83-1f55-4ab5-ae50-7e2eed27c33e"
    answer = "a0b7758e-fef9-47e3-933b-8ce91bd2c3c9"

    class OwnedReplyDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.sent = False
            self.observed = False
            self.sends = 0

        async def eval(self, _script: str, *, main_world: bool = False) -> str | bool:
            if "location.pathname" in _script:
                return f"/c/{chat}" if self.sent else "/"
            return True

        async def click_send(self, expected_message: str) -> None:
            await super().click_send(expected_message)
            self.sent = True
            self.sends += 1

        async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
            if self.observed:
                await asyncio.sleep(min(timeout, 0.01))
                return None
            self.observed = True
            return normalize_dom_snapshot(
                {
                    "pathname": f"/c/{chat}",
                    "message_id": "unit:assistant",
                    "branch_message_id": answer,
                    "text": "Exact answer",
                    "complete": True,
                }
            )

    driver = OwnedReplyDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        connector_approval=False,
    )
    sender.results.ensure_queued("owned-send", "Private prompt")
    await sender._send_browser("Private prompt", send_id="owned-send")
    row = sender.results.get("owned-send")
    assert row is not None
    assert (row["status"], row["conversation_id"], row["message_id"]) == (
        "completed",
        chat,
        answer,
    )
    assert row["assistant_text"] == "Exact answer"
    reply = ManualReplyStore(sender.results.path).prepare(
        "owned-send", ReplyIntent("reply-1234567890123", chat, answer, "Follow-up")
    )
    assert reply["status"] == "prepared" and reply["parent_id"] == answer
    assert driver.sends == 1 and driver.closed_contexts == ["fresh-tab"]


@pytest.mark.asyncio
async def test_tool_only_dom_activity_is_saved_before_capture_disconnects(tmp_path: Path) -> None:
    calls: tuple[dict[str, object], ...] = (
        {
            "id": "dom-tool-0",
            "connector": "",
            "action": "Used Calendar",
            "status": "observed",
        },
    )

    class ToolOnlyDriver(FakeDriver):
        async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
            self.is_connected = False
            return CaptureResult(
                "dom",
                "unknown",
                "",
                "chat",
                "message",
                None,
                tool_calls=calls,
            )

    driver = ToolOnlyDriver()
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", connector_approval=False)
    sender.results.ensure_queued("dom-tools", "Check calendar")
    assert sender.results.accept("dom-tools", "100:owner", deadline=time.time() + 10)
    await sender._capture_until_complete(
        driver,
        driver.capture,
        "dom-tools",
        "100:owner",
        deadline=asyncio.get_running_loop().time() + 10,
    )
    detail = sender.results.detail("dom-tools")
    assert detail is not None
    assert detail["status"] == "interrupted"
    assert detail["tool_calls"] == list(calls)
    assert detail["assistant_text"] == ""
