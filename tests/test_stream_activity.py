"""SSE ordering preserves visible prose and tool calls without private reasoning."""

from __future__ import annotations

import json
from pathlib import Path

from prompta.display_blocks_store import deserialize_display_blocks, merge_display_blocks
from prompta.response_capture import SseResponseAccumulator, parse_sse_body
from prompta.response_store import ResponseStore


def _event(message: dict[str, object]) -> str:
    return "data: " + json.dumps({"message": message}) + "\n\n"


def _message(identity: str, channel: str, text: str) -> dict[str, object]:
    return {
        "id": identity,
        "author": {"role": "assistant"},
        "recipient": "all",
        "channel": channel,
        "content": {"content_type": "text", "parts": [text]},
    }


def _tool(identity: str, action: str) -> dict[str, object]:
    return {
        "id": identity,
        "author": {"role": "assistant"},
        "recipient": "python",
        "content": {"content_type": "code", "parts": [action]},
    }


def _blocks() -> str:
    return "".join(
        (
            _event(_message("opening-1", "commentary", "OPEN")),
            'data: {"o":"append","p":"/message/content/parts/0","v":"ING"}\n\n',
            _event(_tool("call-1", "first()")),
            _event(
                {
                    "id": "result-1",
                    "author": {"role": "tool"},
                    "content": {"content_type": "text", "parts": ["ok"]},
                }
            ),
            _event(_message("private-1", "analysis", "INTERNAL THOUGHT")),
            'data: {"o":"append","p":"/message/content/parts/0","v":" SECRET"}\n\n',
            _event(_message("middle-1", "commentary", "MIDDLE")),
            _event(_tool("call-2", "second()")),
            _event({**_message("final-1", "final", "FINISH"), "end_turn": True}),
            "data: [DONE]\n\n",
        )
    )


def test_interleaved_sse_blocks_are_safe_and_ordered() -> None:
    result = parse_sse_body(_blocks())
    assert result.status == "complete"
    assert result.text == "FINISH"
    assert [block["kind"] for block in result.display_blocks] == [
        "text",
        "tool",
        "text",
        "tool",
        "text",
    ]
    assert [block["text"] for block in result.display_blocks if block["kind"] == "text"] == [
        "OPENING",
        "MIDDLE",
        "FINISH",
    ]
    assert [block["tool_id"] for block in result.display_blocks if block["kind"] == "tool"] == [
        "call-1",
        "call-2",
    ]
    assert "SECRET" not in str(result)
    assert "INTERNAL THOUGHT" not in str(result)


def test_streaming_snapshots_keep_stable_ids_and_sqlite_order(tmp_path: Path) -> None:
    accumulator = SseResponseAccumulator()
    accumulator.feed(_event(_message("opening-1", "commentary", "OPEN")))
    partial = accumulator.snapshot()
    assert partial.text == ""
    assert [block["text"] for block in partial.display_blocks] == ["OPEN"]

    accumulator.feed('data: {"o":"append","p":"/message/content/parts/0","v":"ING"}\n\n')
    accumulator.feed(_event(_tool("call-1", "first()")))
    later = accumulator.snapshot()
    assert later.display_blocks[0]["id"] == partial.display_blocks[0]["id"]
    assert later.display_blocks[0]["text"] == "OPENING"
    assert later.display_blocks[1]["tool_id"] == "call-1"

    accumulator.feed(_event({**_message("final-1", "final", "FINISH"), "end_turn": True}))
    accumulator.feed("data: [DONE]\n\n")
    final = accumulator.snapshot()
    store = ResponseStore(tmp_path / "results.db")
    store.ensure_queued("run", "Check ordering", now=1)
    assert store.accept("run", "owner", deadline=100, now=2)
    assert store.write("run", "owner", partial, now=3)
    assert store.write("run", "owner", later, now=4)
    assert store.write("run", "owner", final, now=5)
    detail = store.detail("run")
    assert detail is not None
    assert detail["display_blocks"] == list(final.display_blocks)
    assert detail["assistant_text"] == "FINISH"

    merged = merge_display_blocks("[]", partial.display_blocks)
    merged = merge_display_blocks(merged, later.display_blocks)
    merged = merge_display_blocks(merged, final.display_blocks)
    merged = merge_display_blocks(merged, final.display_blocks)
    assert deserialize_display_blocks(merged) == list(final.display_blocks)


def test_distinct_commentary_messages_with_same_prose_are_not_deduplicated() -> None:
    result = parse_sse_body(
        _event(_message("first-comment", "commentary", "Checking."))
        + _event(_tool("tool-1", "run()"))
        + _event(_message("second-comment", "commentary", "Checking."))
    )
    assert [block["kind"] for block in result.display_blocks] == ["text", "tool", "text"]
    assert result.display_blocks[0]["id"] != result.display_blocks[2]["id"]


def test_dom_prose_first_seen_survives_hydration_and_tool_interleaving() -> None:
    opening = "Starting investigation: " + "details " * 25
    grown = opening + "more details after refresh"
    first = ({"kind": "text", "id": "text-0", "text": opening,
              "seen_at": "1793798740.125"},)
    merged = merge_display_blocks("[]", first)
    merged = merge_display_blocks(merged, (
        {"kind": "tool", "id": "dom-tool-0"},
        {"kind": "text", "id": "text-0", "text": grown,
         "seen_at": "1793798760.222"},
        {"kind": "text", "id": "text-1", "text": "Conclusion",
         "seen_at": "1793798900.222"},
    ))
    blocks = deserialize_display_blocks(merged)
    assert [block["kind"] for block in blocks] == ["text", "tool", "text"]
    assert blocks[0]["text"] == grown
    assert blocks[0]["seen_at"] == "1793798740.125"
    assert blocks[2]["seen_at"] == "1793798900.222"

    merged = merge_display_blocks("[]", (
        {"kind": "text", "id": "text-0", "text": opening,
         "seen_at": "1793798740.125"},
        {"kind": "tool", "id": "dom-tool-0"},
        {"kind": "text", "id": "text-1", "text": grown,
         "seen_at": "1793798760.222"},
    ))
    normalized = deserialize_display_blocks(merged)
    assert [block["kind"] for block in normalized] == ["text", "tool"]
    assert normalized[0]["seen_at"] == "1793798740.125"
