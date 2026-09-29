from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import pytest

from prompta.delivery_browser import BrowserDeliverySender
from prompta.playwright_driver import PlaywrightDriver


class FakeDriver:
    def __init__(self) -> None:
        self.is_connected = True
        self.needs_browser_restart = False
        self.context = ""
        self.composer = ""
        self.closed_contexts: list[str] = []
        self.closed = False
        self.probe_armed = False
        self.capture: dict[str, Any] = {
            "status": 200,
            "response_started": True,
            "request_id": "request-1",
        }

    async def connect(self) -> None:
        self.is_connected = True

    async def new_tab(self) -> str:
        self.context = "fresh-tab"
        return self.context

    async def wait_for_composer(self) -> None:
        return None

    async def ensure_chat_surface(self) -> None:
        return None

    async def select_effort_model(self, _model: str) -> None:
        return None

    async def set_effort_power_position(self, _position: int) -> dict[str, Any]:
        return {"text": "High", "description": ""}

    async def dismiss_transient_controls(self) -> None:
        return None

    async def dom_state(self) -> dict[str, Any]:
        return {"composer_text": self.composer, "rate_limit_text": ""}

    async def eval(self, _script: str) -> str:
        return "/"

    async def clear_composer(self) -> None:
        self.composer = ""

    async def arm_page_send_probe(self) -> None:
        self.probe_armed = True

    def arm_send_capture(self) -> dict[str, Any]:
        return self.capture

    async def type_message(self, message: str) -> None:
        self.composer = message

    async def click_send(self) -> None:
        self.composer = ""

    async def page_send_probe(self) -> dict[str, Any]:
        return {"committed": True, "response_status": 200}

    def captured_send_response(self, _capture: dict[str, Any]) -> tuple[str, int]:
        return ("request-1", 200)

    def clear_send_capture(self, capture: dict[str, Any]) -> None:
        assert capture is self.capture

    async def clear_page_send_probe(self) -> None:
        self.probe_armed = False

    async def close_context(self, context: str) -> None:
        self.closed_contexts.append(context)

    async def close(self) -> None:
        self.closed = True


@pytest.mark.asyncio
async def test_fresh_chat_is_discarded_immediately_after_dispatch_confirmation(
    tmp_path: Path,
) -> None:
    driver = FakeDriver()
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: cast(PlaywrightDriver, driver),
    )

    await sender._send_browser("Do the scheduled work")

    assert driver.closed_contexts == ["fresh-tab"]
    assert driver.closed is True
    assert driver.probe_armed is False
    assert driver.composer == ""
