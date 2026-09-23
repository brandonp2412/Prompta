from __future__ import annotations

from unittest.mock import AsyncMock

import pytest

from prompta.script_assets import browser_script
from prompta.webdriver import BrowserDriverBase


def test_browser_script_rejects_nested_paths() -> None:
    with pytest.raises(ValueError, match="Invalid browser script name"):
        browser_script("../conversation_final_event.js")


@pytest.mark.asyncio
async def test_ensure_token_loads_standalone_auth_script() -> None:
    driver = BrowserDriverBase()
    driver.eval = AsyncMock(return_value='{"ok":true,"token":"session-token"}')  # type: ignore[method-assign]

    assert await driver.ensure_token() == "session-token"

    driver.eval.assert_awaited_once_with(
        browser_script("auth_session_token.js"),
        await_promise=True,
    )


@pytest.mark.asyncio
async def test_conversation_final_event_passes_id_as_native_script_argument() -> None:
    driver = BrowserDriverBase()
    driver.eval = AsyncMock(return_value='{"ok":true,"status":200,"final_event":null}')  # type: ignore[method-assign]
    conversation_id = 'chat";window.injected=true;//'

    payload = await driver.conversation_final_event(conversation_id, context="context-1")

    assert payload["ok"] is True
    script = browser_script("conversation_final_event.js")
    assert conversation_id not in script
    driver.eval.assert_awaited_once_with(
        script,
        context="context-1",
        await_promise=True,
        argument=conversation_id,
    )
