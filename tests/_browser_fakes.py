from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from prompta.config import ConnectorApproval
from prompta.playwright_driver import _normalise_composer_text
from prompta.response_capture import CaptureResult


@pytest.fixture(autouse=True)
def offline_approval_default(monkeypatch: pytest.MonkeyPatch) -> None:
    # Test behavior must not depend on the host's live connector-approval config.
    monkeypatch.setattr(ConnectorApproval, "load", classmethod(lambda cls: cls(enabled=False)))


class FakeDriver:
    def __init__(self) -> None:
        self.is_connected = True
        self.needs_browser_restart = False
        self.context = ""
        self.composer = ""
        self.closed_contexts: list[str] = []
        self.closed = False
        self.capture: dict[str, object] = {
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

    async def set_effort_power_position(self, _position: int) -> dict[str, object]:
        return {"text": "High", "description": ""}

    async def dismiss_transient_controls(self) -> None:
        return None

    async def dom_state(self) -> dict[str, object]:
        return {"composer_text": self.composer, "rate_limit_text": ""}

    async def send_confirmation_state(self) -> dict[str, object]:
        return {"composer_text": self.composer, "send_in_progress": False}

    async def eval(self, _script: str, *, main_world: bool = False) -> str | bool:
        return "/"

    async def clear_composer(self) -> None:
        self.composer = ""

    def arm_send_capture(self) -> dict[str, object]:
        return self.capture

    async def enable_passive_updates(self) -> None:
        return None

    async def wait_capture_update(self, *, timeout: float) -> CaptureResult | None:
        await asyncio.sleep(min(timeout, 0.01))
        return None

    def captured_assistant_response(self, _capture: dict[str, object]) -> CaptureResult | None:
        return None

    async def observed_assistant_response(self) -> CaptureResult:
        return CaptureResult("dom", "unknown", "", None, None, None)

    async def type_message(self, message: str) -> None:
        self.composer = message

    async def attach_images(self, paths: tuple[Path, ...]) -> None:
        assert not paths

    async def pin_current_chat(self) -> None:
        return None

    async def click_send(self, expected_message: str) -> None:
        assert _normalise_composer_text(self.composer) == _normalise_composer_text(expected_message)
        self.composer = ""

    def captured_send_response(self, _capture: dict[str, object]) -> tuple[str, int] | None:
        return ("request-1", 200)

    def clear_send_capture(self, capture: dict[str, object]) -> None:
        assert capture is self.capture

    async def close_context(self, context: str) -> None:
        self.closed_contexts.append(context)

    async def close(self) -> None:
        self.closed = True
