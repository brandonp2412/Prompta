from __future__ import annotations

import asyncio
import logging
import threading
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from _browser_fakes import FakeDriver
from _browser_fakes import offline_approval_default as offline_approval_default

import prompta.delivery_browser as delivery_browser
import prompta.playwright_driver as playwright_driver
from prompta.delivery_browser import (
    BrowserDeliverySender,
    DeliveryBackendUnavailableError,
    _is_conversation_path,
)
from prompta.playwright_driver import PlaywrightDriver
from prompta.rate_limit import RateLimitError
from prompta.send_outcome import SendOutcomeUnknownError


@pytest.mark.asyncio
async def test_successful_confirmation_polls_do_not_spam_info(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger="prompta.delivery_browser"):
        await delivery_browser._timed_stage(
            "send_confirmation_state",
            asyncio.sleep(0),
            timeout=1,
        )
        await delivery_browser._timed_stage(
            "send_dispatch",
            asyncio.sleep(0),
            timeout=1,
        )
    confirmation = [
        record
        for record in caplog.records
        if "stage=send_confirmation_state" in record.getMessage()
    ]
    assert len(confirmation) == 1 and confirmation[0].levelno == logging.DEBUG
    assert any(
        record.levelno == logging.INFO and "stage=send_dispatch" in record.getMessage()
        for record in caplog.records
    )


@pytest.mark.asyncio
async def test_only_owned_event_stream_marks_live_generation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    request = MagicMock(spec=playwright_driver.Request)
    request.method = "POST"
    response = MagicMock(spec=playwright_driver.Response)
    response.request = request
    response.url = "https://chatgpt.com/backend-api/conversation"
    response.status = 200
    response.headers = {"content-type": "text/event-stream"}
    capture: dict[str, object] = {"request_obj": request, "ambiguous_request": False}
    driver._send_capture = capture
    reader = AsyncMock(return_value=None)
    monkeypatch.setattr(driver, "_read_completed_sse_response", reader)

    driver._on_response(response)
    assert capture["response_started"] is True
    assert capture["sse_stream"] is True
    await asyncio.sleep(0)
    reader.assert_awaited_once()

    capture["sse_stream"] = False
    response.headers = {"content-type": "application/json"}
    driver._on_response(response)
    assert capture["sse_stream"] is False
    capture["ambiguous_request"] = True
    response.headers = {"content-type": "text/event-stream"}
    driver._on_response(response)
    assert capture["sse_stream"] is False


@pytest.mark.asyncio
async def test_owned_tab_lease_precedes_failing_viewport_setup(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    page = MagicMock(spec=playwright_driver.Page)
    session = MagicMock()
    session.send = AsyncMock(return_value={"targetInfo": {"targetId": "owned-target"}})
    session.detach = AsyncMock()
    page.context.new_cdp_session = AsyncMock(return_value=session)
    page.set_viewport_size = AsyncMock(side_effect=RuntimeError("viewport unavailable"))
    page.is_closed.return_value = False
    page.close = AsyncMock()
    registered: list[str] = []
    monkeypatch.setattr(
        playwright_driver,
        "record_owned_tab",
        lambda target_id, _time: registered.append(target_id),
    )
    with pytest.raises(RuntimeError, match="viewport unavailable"):
        await driver._prepare_owned_page(page)
    assert registered == ["owned-target"]
    page.close.assert_awaited()


@pytest.mark.asyncio
async def test_fresh_send_429_respects_transport_retry_after(tmp_path: Path) -> None:
    driver = FakeDriver()
    driver.capture["status"] = 429
    driver.capture["retry_after"] = "600"
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
    )
    with pytest.raises(RateLimitError) as caught:
        await sender._send_browser("Do the scheduled work")
    assert caught.value.retry_after == 600
    assert driver.closed


@pytest.mark.asyncio
async def test_fresh_chat_is_discarded_immediately_after_dispatch_confirmation(
    tmp_path: Path,
) -> None:
    driver = FakeDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
    )

    await sender._send_browser("Do the scheduled work")

    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed is True
    assert driver.composer == ""


@pytest.mark.asyncio
async def test_once_chat_is_pinned_after_acceptance_before_tab_cleanup(tmp_path: Path) -> None:
    actions: list[str] = []

    class PinDriver(FakeDriver):
        async def pin_current_chat(self) -> None:
            actions.append("pin")
            assert self.closed_contexts == []
            assert self.composer == ""

        async def close_context(self, context: str) -> None:
            actions.append("close")
            await super().close_context(context)

    driver = PinDriver()
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", driver_factory=lambda: driver)
    await sender._send_browser("Once job", pin_chat=True)
    assert actions == ["pin", "close"]


@pytest.mark.asyncio
async def test_pin_failure_never_resends_accepted_once_job(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    class PinFailureDriver(FakeDriver):
        async def pin_current_chat(self) -> None:
            raise RuntimeError("Pin control unavailable")

    driver = PinFailureDriver()
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", driver_factory=lambda: driver)
    await sender._send_browser("Once job", pin_chat=True)
    assert "could not be pinned" in caplog.text
    assert driver.closed_contexts == ["fresh-tab"]


@pytest.mark.asyncio
async def test_slow_optional_pin_never_blocks_durable_acceptance(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    pin_started = asyncio.Event()
    release_pin = asyncio.Event()

    class SlowPinDriver(FakeDriver):
        async def pin_current_chat(self) -> None:
            pin_started.set()
            await release_pin.wait()

    driver = SlowPinDriver()
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", driver_factory=lambda: driver)
    sender.results.ensure_queued("pinned-owned-send", "Pin verification")
    acknowledged = threading.Event()
    confirmed = threading.Event()

    async def finish_capture(
        _driver: object,
        _capture: object,
        send_id: str,
        owner: str,
        *,
        deadline: float,
    ) -> None:
        assert deadline > 0
        assert sender.results.finish(send_id, owner, "interrupted")

    monkeypatch.setattr(sender, "_capture_until_complete", finish_capture)
    task = asyncio.create_task(
        sender._send_browser(
            "Pin verification",
            send_id="pinned-owned-send",
            pin_chat=True,
            accepted=acknowledged,
            confirmed=confirmed,
        )
    )
    try:
        await asyncio.wait_for(pin_started.wait(), timeout=2.0)
        # The pin is still blocked, but the send is already durably accepted.
        assert acknowledged.is_set() and confirmed.is_set()
        saved = sender.results.get("pinned-owned-send")
        assert saved is not None and saved["status"] == "accepted"
    finally:
        release_pin.set()
        await asyncio.wait_for(task, timeout=5.0)
    assert driver.closed_contexts == ["fresh-tab"]


def test_delivery_deadline_before_dispatch_is_retryable_and_closes_tab(tmp_path: Path) -> None:
    import asyncio

    class HungPreparationDriver(FakeDriver):
        async def select_effort_model(self, _model: str) -> None:
            await asyncio.Event().wait()

    driver = HungPreparationDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        delivery_hard_timeout_seconds=0.02,
    )

    with pytest.raises(DeliveryBackendUnavailableError, match="deadline expired before dispatch"):
        sender("Do the scheduled work")

    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed is True
    assert driver.composer == ""


@pytest.mark.asyncio
async def test_slow_model_picker_falls_back_with_a_bounded_timeout(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    import asyncio

    class SlowModelPickerDriver(FakeDriver):
        async def select_effort_model(self, _model: str) -> None:
            await asyncio.Event().wait()

    monkeypatch.setattr(delivery_browser, "_MODEL_SELECTION_TIMEOUT_SECONDS", 0.01)
    driver = SlowModelPickerDriver()
    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", driver_factory=lambda: driver)

    await sender._send_browser("Do the scheduled work")

    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed
    assert "stage=model_selection" in caplog.text
    assert "outcome=failed" in caplog.text
    assert "Do the scheduled work" not in caplog.text


@pytest.mark.asyncio
async def test_high_effort_is_selected_before_gpt6(tmp_path: Path) -> None:
    actions: list[str] = []

    class TrackingDriver(FakeDriver):
        async def set_effort_power_position(self, _position: int) -> dict[str, object]:
            actions.append(f"power:{_position}")
            return await super().set_effort_power_position(_position)

        async def select_effort_model(self, _model: str) -> None:
            actions.append(f"model:{_model}")

        async def dismiss_transient_controls(self) -> None:
            actions.append("dismiss")

    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3")
    await sender._ensure_high_effort(TrackingDriver())

    assert actions == ["power:3", "dismiss", "model:GPT-6", "dismiss"]


@pytest.mark.asyncio
async def test_transport_confirmation_precedes_slow_dom_inspection(tmp_path: Path) -> None:
    import asyncio

    class SlowDomAfterDispatchDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.send_dispatched = False
            self.dom_state_calls = 0

        async def dom_state(self) -> dict[str, object]:
            self.dom_state_calls += 1
            if self.send_dispatched:
                await asyncio.Event().wait()
            return await super().dom_state()

        async def click_send(self, expected_message: str) -> None:
            await super().click_send(expected_message)
            self.send_dispatched = True

        def captured_send_response(self, _capture: dict[str, object]) -> tuple[str, int] | None:
            if self.send_dispatched:
                return ("request-1", 200)
            return None

    driver = SlowDomAfterDispatchDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        send_timeout_seconds=0.05,
    )

    await sender._send_browser("Scheduled work")

    assert driver.dom_state_calls == 2
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed


@pytest.mark.asyncio
async def test_transport_arriving_during_slow_dom_check_confirms_once(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    class DelayedTransportDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.send_dispatched = False
            self.transport_ready = False
            self.transport_checks = 0
            self.confirmation_dom_calls = 0

        async def send_confirmation_state(self) -> dict[str, object]:
            if self.send_dispatched:
                self.confirmation_dom_calls += 1
                self.transport_ready = True
                await asyncio.Event().wait()
            return await super().send_confirmation_state()

        async def click_send(self, expected_message: str) -> None:
            await super().click_send(expected_message)
            self.send_dispatched = True

        def captured_send_response(self, _capture: dict[str, object]) -> tuple[str, int] | None:
            self.transport_checks += 1
            if self.transport_ready:
                return ("request-1", 200)
            return None

    monkeypatch.setattr(delivery_browser, "_SEND_CONFIRM_STATE_TIMEOUT_SECONDS", 0.01)
    driver = DelayedTransportDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        send_timeout_seconds=0.05,
    )

    await sender._send_browser("Scheduled work")

    assert driver.confirmation_dom_calls == 1
    assert driver.transport_checks == 2
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed


@pytest.mark.asyncio
async def test_timeout_inside_dispatch_stays_ambiguous_without_retry(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio

    class HungDispatchDriver(FakeDriver):
        def __init__(self) -> None:
            super().__init__()
            self.dispatch_calls = 0

        async def click_send(self, expected_message: str) -> None:
            del expected_message
            self.dispatch_calls += 1
            await asyncio.Event().wait()

        def captured_send_response(self, _capture: dict[str, object]) -> None:
            return None

    monkeypatch.setattr(delivery_browser, "_SEND_DISPATCH_TIMEOUT_SECONDS", 0.01)
    driver = HungDispatchDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        send_timeout_seconds=0.01,
    )

    with pytest.raises(SendOutcomeUnknownError) as error:
        await sender._send_browser("Do the scheduled work")

    assert error.value.stage == "send_dispatch"
    assert driver.dispatch_calls == 1
    assert driver.composer == "Do the scheduled work"
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed


def test_delivery_deadline_during_dispatch_fails_closed_without_resend(tmp_path: Path) -> None:
    import asyncio

    class HungSendDriver(FakeDriver):
        async def click_send(self, expected_message: str) -> None:
            assert self.composer == expected_message
            await asyncio.Event().wait()

    driver = HungSendDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        delivery_hard_timeout_seconds=0.02,
    )

    with pytest.raises(SendOutcomeUnknownError, match="send acceptance is unknown") as error:
        sender("Do the scheduled work")

    assert error.value.stage == "delivery_timeout"
    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed is True
    assert driver.composer == "Do the scheduled work"


@pytest.mark.parametrize(
    ("path", "expected"),
    [
        ("/", False),
        ("/?model=gpt", False),
        ("/c/example", True),
        ("/g/g-p-example/c/example", True),
    ],
)
def test_conversation_route_detection_does_not_parse_identifiers(path: str, expected: bool) -> None:
    assert _is_conversation_path(path) is expected
