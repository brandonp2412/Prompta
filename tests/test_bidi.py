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
async def test_page_send_probe_captures_durable_conversation_id() -> None:
    driver = FirefoxBiDiDriver("ws://unused")
    driver.eval = AsyncMock()  # type: ignore[method-assign]

    await driver.arm_page_send_probe()

    call = driver.eval.await_args
    assert call is not None
    expression = call.args[0]
    assert "conversation_id:''" in expression
    assert """conversation_id["'][ ]*:[ ]*["']""" in expression


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
    assert driver.needs_browser_restart is True


@pytest.mark.asyncio
async def test_connect_retries_transient_firefox_handshake_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeWebSocket:
        close_code = None

    attempts = 0

    async def fake_connect(*args: object, **kwargs: object) -> FakeWebSocket:
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise bidi_module.InvalidMessage("connection closed while reading HTTP status line")
        return FakeWebSocket()

    monkeypatch.setattr(bidi_module.websockets, "connect", fake_connect)
    monkeypatch.setattr(bidi_module, "_BIDI_CONNECT_RETRY_SECONDS", 0.05)
    monkeypatch.setattr(bidi_module, "_BIDI_CONNECT_RETRY_INTERVAL_SECONDS", 0.001)
    driver = FirefoxBiDiDriver("ws://unused")
    driver._call = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {"type": "success"},
            {
                "type": "success",
                "result": {
                    "contexts": [
                        {"context": "live-chat", "url": "https://chatgpt.com/c/123"},
                    ]
                },
            },
            {"type": "success"},
        ]
    )
    driver.login_required = AsyncMock(return_value=False)  # type: ignore[method-assign]
    driver.ensure_token = AsyncMock(return_value=True)  # type: ignore[method-assign]

    await driver.connect()

    assert attempts == 3
    assert driver.context == "live-chat"
    assert driver.needs_browser_restart is False


@pytest.mark.asyncio
async def test_connect_marks_browser_restart_required_when_firefox_session_is_stale(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeWebSocket:
        close_code = None

    async def fake_connect(*args: object, **kwargs: object) -> FakeWebSocket:
        return FakeWebSocket()

    monkeypatch.setattr(bidi_module.websockets, "connect", fake_connect)
    driver = FirefoxBiDiDriver("ws://unused")
    driver._call = AsyncMock(  # type: ignore[method-assign]
        side_effect=RuntimeError(
            "session.new: session not created: Maximum number of active sessions"
        )
    )

    with pytest.raises(RuntimeError, match="Maximum number of active sessions"):
        await driver.connect()

    assert driver.needs_browser_restart is True


@pytest.mark.asyncio
async def test_bidi_call_timeout_is_overall_even_with_event_traffic(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class EventFloodWebSocket:
        close_code = None

        async def send(self, payload: str) -> None:
            return None

        async def recv(self) -> str:
            await asyncio.sleep(0)
            return '{"type":"event","method":"network.beforeRequestSent","params":{}}'

        async def close(self) -> None:
            return None

    monkeypatch.setattr(bidi_module, "_BIDI_CALL_TIMEOUT_SECONDS", 0.01)
    driver = FirefoxBiDiDriver("ws://unused")
    driver.ws = EventFloodWebSocket()
    driver.context = "context-1"

    with pytest.raises(RuntimeError, match="timed out"):
        await driver._call("session.new", {})

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
async def test_conversation_activity_does_not_match_sidebar_stop_titles() -> None:
    driver = FirefoxBiDiDriver("ws://unused")
    driver.eval = AsyncMock(  # type: ignore[method-assign]
        return_value='{"streaming":false,"complete":true,"transient":false,"failed":false}'
    )

    activity = await driver.conversation_activity("context-1")

    assert activity["streaming"] is False
    call = driver.eval.await_args
    assert call is not None
    expression = call.args[0]
    assert 'button[data-testid="stop-button"]' in expression
    assert 'button[aria-label="Stop answering"]' in expression
    assert 'button[aria-label="Stop generating"]' in expression
    assert "const transient=transientText&&!finalAction;" in expression
    assert "const failed=deliveryFailed&&!finalAction&&!stop&&!streamActive;" in expression
    assert "Message delivery timed out" in expression
    assert "const transientText=/(?:Connection interrupted|Waiting for the complete answer)/i" in expression
    assert "testId==='copy-turn-action-button'" in expression
    assert "/^Copy response$/i.test(label)" in expression
    assert "regenerate|share" not in expression
    assert "complete:finalAction&&!stop&&!streamActive" in expression
    assert "&&!transient" not in expression
    assert 'aria-label*="Stop"' not in expression
    assert 'aria-label*="stop"' not in expression


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
    call = driver.eval.await_args
    assert call is not None
    expression = call.args[0]
    assert ".agent-turn" in expression
    assert "const agentRoot=node=>" in expression
    assert "const seededAssistantTurns=new Set()" in expression
    assert "const entryNodes=roleNodes.filter" in expression
    assert "const entries=entryNodes.map" in expression
    assert "...assistantNodes.map(agentRoot).filter(Boolean)" in expression
    assert "for(const [agentIndex,agent] of candidates.entries())" in expression
    assert "content.length>=entries[existing].content.length" in expression
    assert "content.startsWith(message.content)" in expression
    assert "hash(turnSeed)" in expression
    assert "request-placeholder-" in expression
    assert "if(id.startsWith('request-placeholder-'))continue;" in expression
    assert "compareDocumentPosition" in expression
    assert ".join('\\n\\n')" in expression
    assert "const markdownText=root=>" in expression
    assert "data-tool-call-id" in expression
    assert 'data-testid*="search" i' not in expression
    assert "Open tool call list" in expression
    assert "message delivery timed out" in expression.lower()
    assert "conversation-turn-" in expression
    assert "line.includes(text)" in expression
    assert "!node.querySelector(toolSelector)" in expression
    assert "blocks.indexOf(block)===index" in expression
    assert "const seenRoleKeys=new Set()" in expression
    assert "const activity=!richText.length&&!tools.length&&activityLines.length" in expression
    assert "'```tool:'+label" in expression
    assert '[data-streaming="active"]' in expression
    assert 'button[data-testid="stop-button"]' in expression
    assert 'aria-label*="Stop"' not in expression
    assert 'aria-label*="stop"' not in expression
    assert '[aria-busy="true"]' not in expression
    assert "group-data-stream-active" not in expression
    assert "clone.querySelectorAll('button,[role=\"button\"]')" in expression
    assert "'Show moreShow less','Show lessShow more'" in expression
    assert "content:role==='assistant'?rich:messageText(e)" in expression
    assert "normalise(messageText(precedingUser))" in expression


@pytest.mark.asyncio
async def test_dom_state_excludes_message_action_controls() -> None:
    driver = FirefoxBiDiDriver("ws://unused")
    driver.eval = AsyncMock(
        return_value='{"composer_text":"","last_user_id":"u1","last_user_text":"Long prompt","rate_limit_text":""}'
    )  # type: ignore[method-assign]

    state = await driver.dom_state()

    assert state["last_user_text"] == "Long prompt"
    call = driver.eval.await_args
    assert call is not None
    expression = call.args[0]
    assert "clone.querySelectorAll('button,[role=\"button\"]')" in expression
    assert "'Show moreShow less','Show lessShow more'" in expression
    assert "last_user_text:messageText(users.at(-1))" in expression


@pytest.mark.asyncio
async def test_attach_files_ignores_persistent_upload_controls(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attachment = tmp_path / "sample.txt"
    attachment.write_text("hello")
    driver = FirefoxBiDiDriver("ws://unused")
    driver.context = "context-1"
    driver._call = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            {
                "result": {
                    "result": {
                        "type": "node",
                        "sharedId": "file-input-1",
                    }
                }
            },
            {"type": "success"},
        ]
    )
    driver.eval = AsyncMock(  # type: ignore[method-assign]
        side_effect=[
            '{"attached":true,"busy":false}',
            '{"attached":true,"busy":false}',
            '{"attached":true,"busy":false}',
        ]
    )
    monkeypatch.setattr(bidi_module.asyncio, "sleep", AsyncMock())

    await driver.attach_files([str(attachment)])

    assert driver.eval.await_count == 3
    expression = driver.eval.await_args_list[0].args[0]
    assert "uploading|processing|attaching|cancel upload" in expression
    assert "progressBusy" in expression


@pytest.mark.asyncio
async def test_click_send_button_uses_trusted_pointer_action() -> None:
    driver = FirefoxBiDiDriver("ws://unused")
    driver.context = "context-1"
    driver.eval = AsyncMock(return_value='{"x":120.4,"y":240.6}')  # type: ignore[method-assign]
    driver._call = AsyncMock(return_value={"type": "success"})  # type: ignore[method-assign]

    await driver.click_send_button()

    calls = driver._call.await_args_list  # type: ignore[attr-defined]
    assert calls[0].args[0] == "input.performActions"
    actions = calls[0].args[1]["actions"][0]
    assert actions["type"] == "pointer"
    assert actions["actions"][0]["x"] == 120
    assert actions["actions"][0]["y"] == 241
    assert actions["actions"][1] == {"type": "pointerDown", "button": 0}
    assert actions["actions"][2] == {"type": "pointerUp", "button": 0}
    assert calls[1].args[0] == "input.releaseActions"
