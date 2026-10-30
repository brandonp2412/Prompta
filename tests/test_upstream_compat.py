"""Regression checks for upstream ChatGPT web compatibility hardening."""

import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

import prompta.delivery_browser as delivery_browser
from prompta.delivery_browser import BrowserDeliverySender
from prompta.playwright_driver import PlaywrightDriver
from prompta.response_capture import parse_sse_body


def test_reasoning_only_stream_is_explicitly_non_final() -> None:
    payload = (
        'data: {"message":{"id":"thought","author":{"role":"assistant"},'
        '"channel":"analysis","content":{"content_type":"text",'
        '"parts":["private scratchpad"]}}}\n\n'
        "data: [DONE]\n\n"
    )
    result = parse_sse_body(payload)
    assert result.ended_without_answer is True
    assert result.text == ""
    assert result.status == "unknown"
    assert "private scratchpad" not in repr(result)


def test_reasoning_followed_by_final_is_not_an_empty_terminal_turn() -> None:
    payload = (
        'data: {"message":{"id":"thought","author":{"role":"assistant"},'
        '"channel":"analysis","content":{"content_type":"text",'
        '"parts":["private scratchpad"]}}}\n\n'
        'data: {"message":{"id":"answer","author":{"role":"assistant"},'
        '"channel":"final","recipient":"all","content":{"content_type":"text",'
        '"parts":["Public response"]}}}\n\n'
        "data: [DONE]\n\n"
    )
    result = parse_sse_body(payload)
    assert result.ended_without_answer is False
    assert result.text == "Public response"
    assert result.status == "complete"


@pytest.mark.asyncio
async def test_late_accepted_transport_is_not_classified_as_unsent(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    from test_delivery_browser import FakeDriver

    class LateAckDriver(FakeDriver):
        transport_ready = False
        send_clicks = 0

        async def click_send(self, expected_message: str) -> None:
            await super().click_send(expected_message)
            self.send_clicks += 1

        async def send_confirmation_state(self) -> dict[str, object]:
            # The POST callback arrives *after* the final UI probe and before
            # the send deadline expires. No second click is ever acceptable.
            asyncio.get_running_loop().call_later(0.01, setattr, self, "transport_ready", True)
            return await super().send_confirmation_state()

        def captured_send_response(
            self,
            _capture: dict[str, object],
        ) -> tuple[str, int] | None:
            return ("request-1", 200) if self.transport_ready else None

    driver = LateAckDriver()
    monkeypatch.setattr(delivery_browser, "_SEND_CONFIRM_POLL_SECONDS", 0.05)
    sender = BrowserDeliverySender(
        tmp_path / "runtime.sqlite3",
        driver_factory=lambda: driver,
        send_timeout_seconds=0.02,
        connector_approval=False,
    )
    # Override the production lower bound only for this tiny deterministic race.
    sender.send_timeout_seconds = 0.02
    with caplog.at_level("INFO"):
        await asyncio.wait_for(sender._send_browser("One shot only"), timeout=5.0)
    assert driver.send_clicks == 1
    assert "late_transport_confirmed=true" in caplog.text
    assert driver.closed_contexts == ["fresh-tab"]


@pytest.mark.asyncio
async def test_camera_capture_input_is_never_used_for_image_attachment(
    tmp_path: Path,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    page = MagicMock()

    def locate(selector: str) -> MagicMock:
        result = MagicMock()
        # A camera-only input should not match any of the allowed selectors.
        result.count = AsyncMock(return_value=0 if ":not([capture])" in selector else 1)
        result.first.is_enabled = AsyncMock(return_value=True)
        return result

    page.locator.side_effect = locate
    driver._composer = AsyncMock(return_value=None)  # type: ignore[method-assign]
    assert await driver._image_input(page) is None
    assert all(":not([capture])" in call.args[0] for call in page.locator.call_args_list)


@pytest.mark.asyncio
async def test_recognised_composer_promotion_uses_only_safe_dismissal(
    tmp_path: Path,
) -> None:
    driver = PlaywrightDriver(profile=tmp_path / "profile")
    page = MagicMock()
    dialogs = page.get_by_role.return_value
    dialogs.count = AsyncMock(return_value=1)
    dialog = dialogs.nth.return_value
    dialog.is_visible = AsyncMock(return_value=True)
    dialog.inner_text = AsyncMock(return_value="Try thinking effort on your next chat")
    dismiss_button = MagicMock()
    dismiss_button.click = AsyncMock()
    driver._first_usable = AsyncMock(return_value=dismiss_button)  # type: ignore[method-assign]

    assert await driver._dismiss_known_composer_promo(page) is True
    dismiss_button.click.assert_awaited_once_with(timeout=1500)
    assert dialog.get_by_role.call_args.kwargs["name"].pattern == "^(close|dismiss|not now)$"

    dialog.inner_text = AsyncMock(return_value="Confirm deletion of this conversation")
    assert await driver._dismiss_known_composer_promo(page) is False
    assert dismiss_button.click.await_count == 1
