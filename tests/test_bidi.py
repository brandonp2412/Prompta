from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

import pytest

import prompta.bidi as bidi_module
from prompta.bidi import FirefoxBiDiDriver


@pytest.mark.asyncio
async def test_click_send_uses_trusted_enter_on_focused_composer() -> None:
    driver = FirefoxBiDiDriver("ws://unused")
    driver.context = "context-1"
    driver._focus_composer = AsyncMock()  # type: ignore[method-assign]
    driver._key_text = AsyncMock()  # type: ignore[method-assign]

    await driver.click_send()

    driver._focus_composer.assert_awaited_once_with()
    driver._key_text.assert_awaited_once_with("", enter=True)


@pytest.mark.asyncio
async def test_bidi_call_timeout_disconnects_wedged_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class HangingWebSocket:
        close_code = None

        async def send(self, payload: str) -> None:
            return None

        async def recv(self) -> str:
            await asyncio.sleep(10)
            return "{}"

        async def close(self) -> None:
            return None

    monkeypatch.setattr(bidi_module, "_BIDI_CALL_TIMEOUT_SECONDS", 0.01)
    driver = FirefoxBiDiDriver("ws://unused")
    driver.ws = HangingWebSocket()
    driver.context = "context-1"

    with pytest.raises(RuntimeError, match="timed out"):
        await driver._call("script.evaluate", {})

    assert driver.ws is None
    assert driver.context == ""
