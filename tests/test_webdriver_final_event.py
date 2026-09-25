from typing import Any, cast

import pytest

from prompta.webdriver import BrowserDriverBase


class CapturingDriver:
    expression = ""

    async def eval(self, expression: str, **_: Any) -> str:
        self.expression = expression
        return "{}"


@pytest.mark.asyncio
async def test_conversation_final_event_emits_valid_newline_join_expression() -> None:
    driver = CapturingDriver()

    await BrowserDriverBase.conversation_final_event(
        cast(BrowserDriverBase, driver), "conversation-1"
    )

    assert "parts.join(String.fromCharCode(10))" in driver.expression
    assert "parts.join('\n')" not in driver.expression
    assert "let latestUser=null" in driver.expression
    assert "latest_user:latestUser" in driver.expression
