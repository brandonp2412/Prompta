from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

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
