from __future__ import annotations

import json
import shutil

import pytest

from prompta.chromium import _REACT_TOOL_SCRIPT
from prompta.conversation_snapshot import CONVERSATION_SNAPSHOT_SCRIPT
from prompta.transcript_browser_engine import TRANSCRIPT_BROWSER_ENGINE_SCRIPT
from prompta.webdriver import BrowserDriverBase


def _shared_path_results(messages: list[dict]) -> tuple[dict, dict]:
    executable = shutil.which("chromium") or shutil.which("brave")
    if executable is None:
        pytest.skip("A Chromium-compatible browser is unavailable")

    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(executable_path=executable, headless=True)
        try:
            page = browser.new_page()
            page.set_content("<main id='root'></main>")
            page.evaluate(
                """messages => {
                  const root=document.querySelector('#root');
                  root['__reactFiber$shared-engine-test']={
                    memoizedProps:{messages}
                  };
                }""",
                messages,
            )
            snapshot = json.loads(page.evaluate(CONVERSATION_SNAPSHOT_SCRIPT))
            live = page.evaluate(_REACT_TOOL_SCRIPT)
        finally:
            browser.close()
    return snapshot, live


def _source_messages() -> list[dict]:
    return [
        {
            "id": "call-1",
            "parent_id": "reason-1",
            "create_time": 101.0,
            "end_turn": False,
            "status": "finished_successfully",
            "author": {"role": "assistant"},
            "recipient": "api_tool.call_tool",
            "content": {
                "content_type": "code",
                "text": json.dumps(
                    {
                        "path": "/Glass Serena/link_123/serena_repl",
                        "args": {"expression": "1 + 1"},
                    }
                ),
            },
            "metadata": {
                "connector_tool_payload": json.dumps({"expression": "1 + 1"}),
                "reasoning_title": "Checking",
                "model_slug": "gpt-test",
                "request_id": "request-1",
            },
        },
        {
            "id": "result-1",
            "parent_id": "call-1",
            "create_time": 102.0,
            "end_turn": False,
            "author": {"role": "tool"},
            "recipient": "assistant",
            "content": {
                "content_type": "code",
                "text": json.dumps({"text": json.dumps({"stdout": "2"})}),
            },
            "metadata": {
                "invoked_resource": {
                    "app_name": "Glass Serena",
                    "resource_uri": "/asdk_app_123/link_123/serena_repl",
                },
                "jit_plugin_data": {"from_server": {"body": {"connector_name": "Glass Serena"}}},
            },
        },
        {
            "id": "final-1",
            "parent_id": "result-1",
            "create_time": 103.0,
            "end_turn": True,
            "author": {"role": "assistant"},
            "recipient": "all",
            "content": {"content_type": "text", "parts": ["Finished"]},
            "metadata": {
                "attachments": [{"name": "result.txt"}],
                "citations": [{"url": "https://example.invalid"}],
                "content_references": [{"type": "example"}],
            },
        },
    ]


def test_snapshot_and_live_react_paths_share_source_event_semantics() -> None:
    snapshot, live = _shared_path_results(_source_messages())

    assert live["messages"] == snapshot["source_events"]
    assert [event["id"] for event in live["messages"]] == ["call-1", "result-1", "final-1"]
    assert live["messages"][0]["reasoning_title"] == "Checking"
    assert live["messages"][1]["connector_name"] == "Glass Serena"
    assert live["messages"][2]["attachments"] == [{"name": "result.txt"}]
    diagnostics = snapshot["extraction_diagnostics"]
    assert diagnostics["message_provenance"] == ["react-private-properties"]
    assert diagnostics["source_event_provenance"] == ["react-private-properties"]
    assert diagnostics["fallback_used"] is True
    assert "transcript-gap" in diagnostics["fallback_reasons"]
    assert diagnostics["unreconciled_expected_content"] == []


def test_snapshot_and_live_scripts_embed_the_same_transcript_engine_once() -> None:
    marker = "const promptaTranscriptEngine=(()=>{"

    assert marker in TRANSCRIPT_BROWSER_ENGINE_SCRIPT
    assert CONVERSATION_SNAPSHOT_SCRIPT.count(marker) == 1
    assert _REACT_TOOL_SCRIPT.count(marker) == 1


@pytest.mark.asyncio
async def test_webdriver_snapshot_remains_a_thin_shared_engine_adapter() -> None:
    calls: list[tuple[str, str | None]] = []

    class Driver(BrowserDriverBase):
        async def eval(
            self,
            expression: str,
            *,
            await_promise: bool = False,
            context: str | None = None,
        ):
            calls.append((expression, context))
            return json.dumps({"messages": [{"id": "assistant-1"}]})

    driver = Driver()

    assert await driver.conversation_snapshot("context-1") == {"messages": [{"id": "assistant-1"}]}
    assert calls == [(CONVERSATION_SNAPSHOT_SCRIPT, "context-1")]


@pytest.mark.asyncio
async def test_webdriver_activity_uses_shared_engine_adapter() -> None:
    calls: list[tuple[str, str | None]] = []

    class Driver(BrowserDriverBase):
        async def eval(
            self,
            expression: str,
            *,
            await_promise: bool = False,
            context: str | None = None,
        ):
            calls.append((expression, context))
            return json.dumps(
                {
                    "streaming": False,
                    "complete": True,
                    "transient": False,
                    "failed": False,
                    "turn_ended": True,
                }
            )

    driver = Driver()

    activity = await driver.conversation_activity("context-activity")

    assert activity["complete"] is True
    assert len(calls) == 1
    script, context = calls[0]
    assert context == "context-activity"
    assert script.count("const promptaTranscriptEngine=(()=>{") == 1
    assert "promptaTranscriptEngine.inspectReact(" in script
    assert "'activity-end-state'" in script
    assert "{maxDepth:7,maxKeys:260}" in script
