from __future__ import annotations

import asyncio
import time
from pathlib import Path

import pytest
from _browser_fakes import FakeDriver
from _browser_fakes import offline_approval_default as offline_approval_default

from prompta.delivery_browser import BrowserDeliverySender
from prompta.response_capture import CaptureResult


@pytest.mark.asyncio
@pytest.mark.parametrize("same_observer", [True, False])
async def test_owned_multi_message_reply_preserves_its_final_backend_parent(
    tmp_path: Path, same_observer: bool,
) -> None:
    """Tool continuations can change backend IDs inside one rendered reply."""
    chat_id = "d5c86e83-1f55-4ab5-ae50-7e2eed27c33e"
    first_id = "a0b7758e-fef9-47e3-933b-8ce91bd2c3c9"
    final_id = "b0b7758e-fef9-47e3-933b-8ce91bd2c3c9"
    snapshots = iter((
        CaptureResult("dom", "partial", "Working...", chat_id, first_id, None, "reply-unit"),
        CaptureResult(
            "dom", "complete", "Working... Done", chat_id, final_id, None,
            "reply-unit" if same_observer else "other-reply-unit",
        ),
    ))

    class MultiMessageDriver(FakeDriver):
        async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
            return next(snapshots, None)

    sender = BrowserDeliverySender(tmp_path / "runtime.sqlite3", connector_approval=False)
    sender.results.ensure_queued("multi-message", "Task with tools")
    owner = "100:owner"
    assert sender.results.accept("multi-message", owner, deadline=time.time() + 30)
    driver = MultiMessageDriver()
    await sender._capture_until_complete(
        driver, driver.capture, "multi-message", owner,
        deadline=asyncio.get_running_loop().time() + 10,
    )
    result = sender.results.get("multi-message")
    assert result is not None
    if same_observer:
        assert result["status"] == "completed"
        assert result["message_id"] == final_id
        assert result["assistant_text"] == "Working... Done"
    else:
        assert result["status"] == "unavailable"
        assert result["message_id"] == first_id
