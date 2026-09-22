from __future__ import annotations

import json
from pathlib import Path

from prompta.cache import ChatCache
from prompta.conversation_snapshot import CONVERSATION_SNAPSHOT_SCRIPT
from prompta.structured_capture import (
    message_parts_from_source_events,
    tool_calls_from_source_events,
)
from prompta.web_store import ReadOnlyChatStore


def _source_events(result_text: str = "RESULT") -> list[dict]:
    return [
        {
            "id": "reason-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Checking the stored conversation state"],
            "text": "",
            "reasoning_title": "Remembering",
            "create_time": 100.0,
            "end_turn": False,
        },
        {
            "id": "call-1",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps(
                {
                    "path": "/Glass Serena/link_123/serena_repl",
                    "args": {"expression": "1 + 1"},
                }
            ),
            "connector_tool_payload": json.dumps({"expression": "1 + 1"}),
            "reasoning_title": "Remembering",
            "create_time": 101.0,
            "end_turn": False,
        },
        {
            "id": "result-1",
            "role": "tool",
            "recipient": "assistant",
            "content_type": "code",
            "text": json.dumps({"text": json.dumps({"stdout": result_text})}),
            "invoked_resource": {
                "app_name": "Glass Serena",
                "resource_uri": "/asdk_app_123/link_123/serena_repl",
            },
            "create_time": 102.0,
            "end_turn": False,
        },
        {
            "id": "final-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Finished"],
            "text": "",
            "reasoning_title": "",
            "create_time": 103.0,
            "end_turn": True,
        },
    ]


def test_browser_source_capture_excludes_unfiltered_react_internals() -> None:
    assert "content:safeJsonValue(content)" not in CONVERSATION_SNAPSHOT_SCRIPT
    assert "metadata:safeJsonValue(metadata)" not in CONVERSATION_SNAPSHOT_SCRIPT
    assert (
        "if(role==='tool'||recipient==='api_tool.call_tool')return true;"
        in CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "if(message?.end_turn===true)return true;" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "visibleAgentText.includes(text)" in CONVERSATION_SNAPSHOT_SCRIPT


def test_browser_snapshot_does_not_replace_visible_prose_with_tool_only_react_content() -> None:
    assert "const reactVisible=normalise(reactOrdered);" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const reactKeepsVisibleText=!richPlain.length||richPlain.every(text=>" in (
        CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "reactVisible.includes(visibleText)" in CONVERSATION_SNAPSHOT_SCRIPT
    assert (
        "const content=((reactOrdered&&reactKeepsVisibleText)?reactOrdered:fallbackContent).trim();"
        in CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert (
        "const content=(reactOrdered||fallbackContent).trim();" not in CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "const markdownNodes=[...agent.querySelectorAll(" in CONVERSATION_SNAPSHOT_SCRIPT
    assert (
        "const markdown=markdownNodes.filter(node=>!toolRows.some(toolRow=>toolRow.contains(node)));"
        in CONVERSATION_SNAPSHOT_SCRIPT
    )


def test_browser_snapshot_filters_transient_connection_noise_from_react_history() -> None:
    assert "const networkErrorNoise=/a network error occurred" in CONVERSATION_SNAPSHOT_SCRIPT
    assert (
        "connection interrupted\\.?(?:\\s*waiting for (?:the )?complete answer"
        in CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert (
        "a network error occurred\\.?(?:\\s*please check your connection and try again"
        in CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert ".replace(networkErrorNoise,'')" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const visibleText=cleanAssistantText(" in CONVERSATION_SNAPSHOT_SCRIPT


def test_browser_snapshot_interleaves_tool_calls_by_invocation_time() -> None:
    assert "prior?.createdAt||Number(message?.create_time)" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "const timeline=textEntries.map(entry=>({" in CONVERSATION_SNAPSHOT_SCRIPT
    assert "time:toolBlockTime(block)??" in CONVERSATION_SNAPSHOT_SCRIPT
    assert (
        "timeline.sort((left,right)=>left.time-right.time||left.order-right.order);"
        in CONVERSATION_SNAPSHOT_SCRIPT
    )
    assert "const parts=[],finalTextParts=[];" not in CONVERSATION_SNAPSHOT_SCRIPT


def test_structured_capture_keeps_reasoning_tool_identity_and_full_result() -> None:
    result_text = "x" * 20_000
    events = _source_events(result_text)

    calls = tool_calls_from_source_events(events)
    parts = message_parts_from_source_events(events)

    assert len(calls) == 1
    assert calls[0]["connector"] == "Glass Serena"
    assert calls[0]["action"] == "serena_repl"
    assert calls[0]["summary"] == "Remembering"
    assert calls[0]["arguments"] == {"expression": "1 + 1"}
    assert calls[0]["result"]["stdout"] == result_text

    assert [part["kind"] for part in parts] == [
        "reasoning",
        "tool_call",
        "final_text",
    ]
    assert parts[0]["title"] == "Remembering"
    assert "Glass Serena · serena_repl" in parts[1]["content"]
    assert parts[-1]["content"] == "Finished"


def test_completed_tool_wrappers_keep_invocation_order_with_interleaved_text() -> None:
    events = [
        {
            "id": "text-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["First text"],
            "create_time": 1.0,
            "end_turn": False,
        },
        {
            "id": "call-1",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps({"path": "/Test MCP/link_123/first", "args": {"step": 1}}),
            "create_time": 2.0,
        },
        {
            "id": "text-2",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Between tools"],
            "create_time": 3.0,
            "end_turn": True,
        },
        {
            "id": "call-2",
            "role": "assistant",
            "recipient": "api_tool.call_tool",
            "content_type": "code",
            "text": json.dumps({"path": "/Test MCP/link_123/second", "args": {"step": 2}}),
            "create_time": 4.0,
        },
        {
            "id": "result-1",
            "role": "tool",
            "recipient": "all",
            "content_type": "code",
            "text": json.dumps(
                {
                    "type": "mcpToolCall",
                    "appContext": {"appName": "Test MCP", "actionName": "first"},
                    "arguments": {"step": 1},
                    "status": "completed",
                }
            ),
            "create_time": 7.0,
        },
        {
            "id": "result-2",
            "role": "tool",
            "recipient": "all",
            "content_type": "code",
            "text": json.dumps(
                {
                    "type": "mcpToolCall",
                    "appContext": {"appName": "Test MCP", "actionName": "second"},
                    "arguments": {"step": 2},
                    "status": "completed",
                }
            ),
            "create_time": 8.0,
        },
        {
            "id": "final-1",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": ["Done"],
            "create_time": 9.0,
            "end_turn": True,
        },
    ]

    calls = tool_calls_from_source_events(events)
    parts = message_parts_from_source_events(events)
    content = "\n\n".join(part["content"] for part in parts)

    assert [call["created_at"] for call in calls] == [2.0, 4.0]
    assert [call["source_event_key"] for call in calls] == ["call-1", "call-2"]
    assert [call["result_event_key"] for call in calls] == ["result-1", "result-2"]
    assert [part["kind"] for part in parts] == [
        "assistant_text",
        "tool_call",
        "assistant_text",
        "tool_call",
        "final_text",
    ]
    assert content.index("First text") < content.index("Test MCP · first")
    assert content.index("Test MCP · first") < content.index("Between tools")
    assert content.index("Between tools") < content.index("Test MCP · second")
    assert content.index("Test MCP · second") < content.index("Done")


def test_snapshot_digest_includes_structured_source_events() -> None:
    base = {
        "title": "Structured",
        "path": "/c/chat",
        "streaming": False,
        "messages": [{"id": "a1", "role": "assistant", "content": "Same answer"}],
        "source_events": [
            {
                "id": "call-1",
                "role": "assistant",
                "recipient": "api_tool.call_tool",
                "reasoning_title": "Remembering",
                "connector_name": "",
            }
        ],
    }
    corrected = {
        **base,
        "source_events": [
            {
                **base["source_events"][0],
                "connector_name": "Glass Serena",
            }
        ],
    }

    assert ChatCache.digest(base) != ChatCache.digest(corrected)


def test_activity_history_is_persisted_without_changing_message_digest(tmp_path: Path) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    cache.start(
        "conversation-state",
        context_id="context-state",
        job_name="",
        prompt="Track state",
    )
    snapshot = {
        "title": "State",
        "path": "/c/conversation-state",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Track state"},
            {"id": "a1", "role": "assistant", "content": "Working"},
        ],
    }
    digest = ChatCache.digest(snapshot)

    cache.record_state(
        "conversation-state",
        {
            "streaming": True,
            "complete": False,
            "transient": False,
            "failed": False,
            "turn_ended": False,
        },
    )
    cache.record_state(
        "conversation-state",
        {
            "streaming": False,
            "complete": True,
            "transient": False,
            "failed": False,
            "turn_ended": True,
        },
    )

    assert ChatCache.digest(snapshot) == digest
    rows = cache.connection.execute(
        """
        SELECT status, streaming, complete, turn_ended
        FROM conversation_state_events
        WHERE conversation_id = ?
        ORDER BY observed_at, id
        """,
        ("conversation-state",),
    ).fetchall()
    cache.close()

    assert [
        (row["status"], row["streaming"], row["complete"], row["turn_ended"]) for row in rows
    ] == [
        ("active", 0, 0, None),
        ("active", 1, 0, 0),
        ("active", 0, 1, 1),
    ]


def test_read_only_store_does_not_drop_canonical_final_text_when_parts_are_stale(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    conversation_id = "conversation-stale-parts"
    cache.start(
        conversation_id,
        context_id="context-1",
        job_name="",
        prompt="Inspect this",
    )
    fence = chr(96) * 3
    tool_block = (
        fence
        + "tool:Glass Serena · serena_repl\n"
        + json.dumps({"status": "completed"})
        + "\n"
        + fence
    )
    final_text = "Fixed and deployed to Nox."
    snapshot = {
        "title": "Structured",
        "path": f"/c/{conversation_id}",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Inspect this"},
            {
                "id": "a1",
                "role": "assistant",
                "content": tool_block + "\n\n" + final_text,
            },
        ],
        "source_events": _source_events(),
    }
    cache.write_snapshot(conversation_id, snapshot, complete=True)
    cache.connection.execute(
        """
        DELETE FROM message_parts
        WHERE conversation_id = ? AND message_key = ? AND kind = 'final_text'
        """,
        (conversation_id, "a1"),
    )
    cache.connection.commit()
    cache.close()

    chat = ReadOnlyChatStore(path).conversation(conversation_id)

    assert chat is not None
    assistant = chat["messages"][-1]
    assert final_text in assistant["content"]
    assert "Glass Serena · serena_repl" in assistant["content"]


def test_cache_persists_structured_events_parts_tools_and_message_versions(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    cache.start(
        "conversation-structured",
        context_id="context-1",
        job_name="",
        prompt="Inspect this",
    )
    events = _source_events()
    snapshot = {
        "title": "Structured",
        "path": "/c/conversation-structured",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Inspect this"},
            {
                "id": "a1",
                "role": "assistant",
                "content": "Checking the stored conversation state\n\nFinished",
            },
        ],
        "source_events": events,
    }
    cache.write_snapshot("conversation-structured", snapshot, complete=True)

    source_count = cache.connection.execute(
        "SELECT COUNT(*) FROM source_events WHERE conversation_id = ?",
        ("conversation-structured",),
    ).fetchone()[0]
    parts = cache.connection.execute(
        """
        SELECT kind, title, content
        FROM message_parts
        WHERE conversation_id = ? AND message_key = ?
        ORDER BY ordinal
        """,
        ("conversation-structured", "a1"),
    ).fetchall()
    tool = cache.connection.execute(
        """
        SELECT connector, action, summary, arguments_json, result_json
        FROM tool_calls
        WHERE conversation_id = ? AND message_key = ?
        """,
        ("conversation-structured", "a1"),
    ).fetchone()
    message = cache.connection.execute(
        """
        SELECT source_created_at
        FROM messages
        WHERE conversation_id = ? AND message_key = ?
        """,
        ("conversation-structured", "a1"),
    ).fetchone()
    version_count = cache.connection.execute(
        """
        SELECT COUNT(*)
        FROM message_versions
        WHERE conversation_id = ? AND message_key = ?
        """,
        ("conversation-structured", "a1"),
    ).fetchone()[0]

    assert source_count == 4
    assert [(row["kind"], row["title"]) for row in parts] == [
        ("reasoning", "Remembering"),
        ("tool_call", "Remembering"),
        ("final_text", ""),
    ]
    assert tool is not None
    assert tool["connector"] == "Glass Serena"
    assert tool["action"] == "serena_repl"
    assert tool["summary"] == "Remembering"
    assert json.loads(tool["arguments_json"]) == {"expression": "1 + 1"}
    assert json.loads(tool["result_json"]) == {"stdout": "RESULT"}
    assert message["source_created_at"] == 100.0
    assert version_count == 1

    chat = ReadOnlyChatStore(path).conversation("conversation-structured")
    assert chat is not None
    assistant = chat["messages"][-1]
    assert assistant["created_at"] == 100.0
    assert assistant["source_event_count"] == 4
    assert assistant["version_count"] == 1
    assert assistant["tool_calls"][0]["connector"] == "Glass Serena"
    assert "Glass Serena · serena_repl" in assistant["content"]
    assert assistant["content"].endswith("Finished")
    assert [event["status"] for event in chat["state_events"]] == ["active", "complete"]
    assert chat["state_events"][-1]["complete"] is True

    revised_events = _source_events()
    revised_events[-1] = {
        **revised_events[-1],
        "parts": ["Finished, revised"],
    }
    snapshot["messages"][1]["content"] = (
        "Checking the stored conversation state\n\nFinished, revised"
    )
    snapshot["source_events"] = revised_events
    cache.write_snapshot("conversation-structured", snapshot, complete=True)

    revised_source_count = cache.connection.execute(
        "SELECT COUNT(*) FROM source_events WHERE conversation_id = ?",
        ("conversation-structured",),
    ).fetchone()[0]
    revised_version_count = cache.connection.execute(
        """
        SELECT COUNT(*)
        FROM message_versions
        WHERE conversation_id = ? AND message_key = ?
        """,
        ("conversation-structured", "a1"),
    ).fetchone()[0]
    raw_final_events = cache.connection.execute(
        """
        SELECT raw_json
        FROM source_events
        WHERE conversation_id = ? AND message_key = ? AND raw_json LIKE '%final-1%'
        ORDER BY observed_at
        """,
        ("conversation-structured", "a1"),
    ).fetchall()
    cache.close()

    assert revised_source_count == 5
    assert revised_version_count == 2
    assert len(raw_final_events) == 2
    assert any("Finished" in row["raw_json"] for row in raw_final_events)
    assert any("Finished, revised" in row["raw_json"] for row in raw_final_events)


def test_partial_structured_capture_preserves_known_assistant_text_parts(
    tmp_path: Path,
) -> None:
    path = tmp_path / "chats.sqlite3"
    cache = ChatCache(path)
    conversation_id = "conversation-partial-structured"
    cache.start(
        conversation_id,
        context_id="context-1",
        job_name="",
        prompt="Inspect this",
    )
    events = _source_events()
    snapshot = {
        "title": "Structured",
        "path": f"/c/{conversation_id}",
        "streaming": True,
        "messages": [
            {"id": "u1", "role": "user", "content": "Inspect this"},
            {
                "id": "a1",
                "role": "assistant",
                "content": "Checking the stored conversation state\n\nFinished",
            },
        ],
        "source_events": events,
    }
    cache.write_snapshot(conversation_id, snapshot)

    snapshot["streaming"] = False
    snapshot["source_events"] = [events[1], events[2]]
    cache.write_snapshot(conversation_id, snapshot, complete=True)

    parts = cache.connection.execute(
        """
        SELECT kind, content
        FROM message_parts
        WHERE conversation_id = ? AND message_key = ?
        ORDER BY ordinal
        """,
        (conversation_id, "a1"),
    ).fetchall()
    source_count = cache.connection.execute(
        "SELECT COUNT(*) FROM source_events WHERE conversation_id = ?",
        (conversation_id,),
    ).fetchone()[0]
    cache.close()

    assert [row["kind"] for row in parts] == ["reasoning", "tool_call", "final_text"]
    assert parts[0]["content"] == "Checking the stored conversation state"
    assert parts[-1]["content"] == "Finished"
    assert source_count == 4

    chat = ReadOnlyChatStore(path).conversation(conversation_id)
    assert chat is not None
    assistant = chat["messages"][-1]
    assert "Checking the stored conversation state" in assistant["content"]
    assert "Glass Serena · serena_repl" in assistant["content"]
    assert assistant["content"].endswith("Finished")


def test_cache_skips_structured_capture_when_transient_target_is_deleted(
    tmp_path: Path,
) -> None:
    cache = ChatCache(tmp_path / "chats.sqlite3")
    conversation_id = "conversation-transient-structured"
    cache.start(
        conversation_id,
        context_id="context-1",
        job_name="",
        prompt="Inspect this",
    )
    stable_snapshot = {
        "title": "Structured",
        "path": f"/c/{conversation_id}",
        "streaming": False,
        "messages": [
            {"id": "u1", "role": "user", "content": "Inspect this"},
            {"id": "a1", "role": "assistant", "content": "Canonical response"},
        ],
    }
    cache.write_snapshot(conversation_id, stable_snapshot)

    transient_snapshot = {
        "title": "Structured",
        "path": f"/c/{conversation_id}",
        "streaming": True,
        "messages": [
            {"id": "u1", "role": "user", "content": "Inspect this"},
            {
                "id": "__prompta_live_assistant_transient",
                "role": "assistant",
                "content": "Different streaming draft",
            },
        ],
        "source_events": _source_events(),
    }
    cache.write_snapshot(conversation_id, transient_snapshot)

    transient = cache.connection.execute(
        """
        SELECT 1
        FROM messages
        WHERE conversation_id = ? AND message_key = ?
        """,
        (conversation_id, "__prompta_live_assistant_transient"),
    ).fetchone()
    transient_parts = cache.connection.execute(
        """
        SELECT COUNT(*)
        FROM message_parts
        WHERE conversation_id = ? AND message_key = ?
        """,
        (conversation_id, "__prompta_live_assistant_transient"),
    ).fetchone()[0]

    stable_snapshot["source_events"] = _source_events()
    cache.write_snapshot(conversation_id, stable_snapshot, complete=True)
    stable_parts = cache.connection.execute(
        """
        SELECT COUNT(*)
        FROM message_parts
        WHERE conversation_id = ? AND message_key = ?
        """,
        (conversation_id, "a1"),
    ).fetchone()[0]
    cache.close()

    assert transient is None
    assert transient_parts == 0
    assert stable_parts > 0


def test_structured_capture_ignores_network_error_banner_between_tool_activity() -> None:
    events = _source_events()
    events.insert(
        2,
        {
            "id": "network-error",
            "role": "assistant",
            "recipient": "all",
            "content_type": "text",
            "parts": [
                "A network error occurred. Please check your connection and try again. If this issue persists please contact us through our help center at help.openai.com."
            ],
            "text": "",
            "reasoning_title": "",
            "create_time": 101.5,
            "end_turn": False,
        },
    )

    parts = message_parts_from_source_events(events)
    combined = "\n".join(str(part.get("content") or "") for part in parts)

    assert "A network error occurred" not in combined
    assert "Checking the stored conversation state" in combined
    assert "Finished" in combined
