from __future__ import annotations

import json
from pathlib import Path

from prompta.cache import ChatCache
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

    revised_events = _source_events()
    revised_events[-1] = {
        **revised_events[-1],
        "parts": ["Finished, revised"],
    }
    snapshot["messages"][1]["content"] = "Checking the stored conversation state\n\nFinished, revised"
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
