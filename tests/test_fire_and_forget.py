"""Send-only behavior must not accidentally reintroduce ChatGPT reads."""

from __future__ import annotations

from pathlib import Path

import pytest
from _browser_fakes import FakeDriver

from prompta.delivery_browser import BrowserDeliverySender
from prompta.response_capture import CaptureResult
from prompta.send_outcome import SendOutcomeUnknownError


class NoReadDriver(FakeDriver):
    def __init__(self) -> None:
        super().__init__()
        self.sends = 0

    def arm_send_capture(self) -> dict[str, object]:
        raise AssertionError("send capture must be disabled")

    async def dom_state(self) -> dict[str, object]:
        raise AssertionError("status reads must be disabled")

    async def send_confirmation_state(self) -> dict[str, object]:
        raise AssertionError("confirmation reads must be disabled")

    async def observed_assistant_response(self) -> CaptureResult:
        raise AssertionError("response reads must be disabled")

    async def eval(self, _script: str, *, main_world: bool = False) -> str:
        raise AssertionError("remote page reads must be disabled")

    async def click_send(self, expected_message: str) -> None:
        await super().click_send(expected_message)
        self.sends += 1


@pytest.mark.parametrize("send_id", ["manual-123", "scheduled-123"])
def test_send_only_records_submitted_without_response_reads(tmp_path: Path, send_id: str) -> None:
    driver = NoReadDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3", driver_factory=lambda: driver,
        fire_and_forget=True, connector_approval=False,
    )

    sender("Make a change", send_id=send_id, job_name="test")
    record = sender.results.get(send_id)
    assert record is not None
    assert record["status"] == "submitted"
    assert record["source"] == "fire_and_forget"
    assert record["assistant_text"] == ""
    assert record["capture_owner"] == ""
    assert driver.sends == 1
    assert driver.closed
    assert not driver.closed_contexts

    # A durable submitted receipt must never submit the same idempotency key again.
    sender("Make a change", send_id=send_id, job_name="test")
    assert driver.sends == 1


def test_failed_send_action_is_quarantined_not_retried(tmp_path: Path) -> None:
    class UncertainDriver(NoReadDriver):
        async def click_send(self, expected_message: str) -> None:
            raise RuntimeError("button click uncertain")

    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3", driver_factory=UncertainDriver,
        fire_and_forget=True, connector_approval=False,
    )
    with pytest.raises(SendOutcomeUnknownError):
        sender("Make a change", send_id="uncertain")
    uncertain = sender.results.get("uncertain")
    assert uncertain is not None
    assert uncertain["status"] == "queued"


def test_send_only_never_reports_response_complete(tmp_path: Path) -> None:
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3", driver_factory=NoReadDriver,
        fire_and_forget=True, connector_approval=False,
    )
    sender("Do the work", send_id="sent")
    summary = sender.results.get("sent")
    assert summary is not None
    assert summary["status"] != "completed"
    finished_at = summary["finished_at"]
    assert isinstance(finished_at, (int, float)) and finished_at > 0
