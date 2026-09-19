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


@pytest.mark.asyncio
async def test_eval_reports_browser_side_script_exception() -> None:
    driver = FirefoxBiDiDriver("ws://unused")
    driver.context = "context-1"
    driver._call = AsyncMock(  # type: ignore[method-assign]
        return_value={
            "result": {
                "type": "exception",
                "exceptionDetails": {"text": "ReferenceError: broken"},
            }
        }
    )

    with pytest.raises(RuntimeError, match="ReferenceError: broken"):
        await driver.eval("broken()")


@pytest.mark.asyncio
async def test_connect_reuses_existing_chatgpt_context_without_navigation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeWebSocket:
        close_code = None

    async def fake_connect(*args: object, **kwargs: object) -> FakeWebSocket:
        return FakeWebSocket()

    monkeypatch.setattr(bidi_module.websockets, "connect", fake_connect)
    driver = FirefoxBiDiDriver("ws://unused")
    driver._call = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"type": "success"},
            {
                "type": "success",
                "result": {
                    "contexts": [
                        {"context": "other", "url": "about:blank"},
                        {
                            "context": "live-chat",
                            "url": "https://chatgpt.com/c/123",
                        },
                    ]
                },
            },
            {"type": "success"},
        ]
    )
    driver.navigate = AsyncMock()  # type: ignore[method-assign]
    driver.login_required = AsyncMock(return_value=False)  # type: ignore[method-assign]
    driver.ensure_token = AsyncMock(return_value=True)  # type: ignore[method-assign]

    await driver.connect()

    assert driver.context == "live-chat"
    driver.navigate.assert_not_awaited()


@pytest.mark.asyncio
async def test_connect_navigates_only_when_no_chatgpt_context_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeWebSocket:
        close_code = None

    async def fake_connect(*args: object, **kwargs: object) -> FakeWebSocket:
        return FakeWebSocket()

    monkeypatch.setattr(bidi_module.websockets, "connect", fake_connect)
    driver = FirefoxBiDiDriver("ws://unused")
    driver._call = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"type": "success"},
            {
                "type": "success",
                "result": {
                    "contexts": [
                        {"context": "blank", "url": "about:blank"},
                    ]
                },
            },
            {"type": "success"},
        ]
    )
    driver.navigate = AsyncMock()  # type: ignore[method-assign]
    driver.login_required = AsyncMock(return_value=False)  # type: ignore[method-assign]
    driver.ensure_token = AsyncMock(return_value=True)  # type: ignore[method-assign]

    await driver.connect()

    assert driver.context == "blank"
    driver.navigate.assert_awaited_once_with("https://chatgpt.com/")


@pytest.mark.asyncio
async def test_conversation_snapshot_uses_live_agent_turn_fallback() -> None:
    driver = FirefoxBiDiDriver("ws://unused")
    driver.eval = AsyncMock(  # type: ignore[method-assign]
        return_value='{"path":"/c/WEB:test","title":"Live","messages":[{"id":"__prompta_live_assistant__","role":"assistant","content":"Working","ordinal":1}],"streaming":true}'
    )

    snapshot = await driver.conversation_snapshot("context-1")

    assert snapshot["messages"][-1] == {
        "id": "__prompta_live_assistant__",
        "role": "assistant",
        "content": "Working",
        "ordinal": 1,
    }
    assert snapshot["streaming"] is True
    expression = driver.eval.await_args.args[0]
    assert ".agent-turn" in expression
    assert "for(const [agentIndex,agent] of candidates.entries())" in expression
    assert "content.length>=entries[existing].content.length" in expression
    assert "content.startsWith(message.content)" in expression
    assert "hash(turnSeed)" in expression
    assert "compareDocumentPosition" in expression
    assert ".join('\n\n')" in expression
    assert '[data-streaming="active"]' in expression
    assert "group-data-stream-active" not in expression
