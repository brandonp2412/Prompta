"""Visible commentary remains distinct and ordered across capture, SQLite and replies."""

from pathlib import Path

from prompta.display_blocks_store import deserialize_display_blocks, merge_display_blocks
from prompta.reply_contracts import ManualReplyStore
from prompta.response_capture import normalize_dom_snapshot
from prompta.response_store import ResponseStore


def test_visible_blocks_persist_across_partial_and_complete_frames(tmp_path: Path) -> None:
    store = ResponseStore(tmp_path / "results.db")
    store.ensure_queued("run", "Check a file", now=1)
    assert store.accept("run", "123:owner", deadline=100, now=2)
    before = normalize_dom_snapshot({
        "message_id": "owned-turn", "pathname": "/c/12345678-1234-4123-8123-123456789abc",
        "text": "I'll check.",
        "display_blocks": [{"kind": "text", "id": "text-0", "text": "I'll check."}],
    })
    assert store.write("run", "123:owner", before, now=3)
    after = normalize_dom_snapshot({
        "message_id": "owned-turn", "pathname": "/c/12345678-1234-4123-8123-123456789abc",
        "text": "I'll check.\n\nFound it.",
        "display_blocks": [
            {"kind": "text", "id": "text-0", "text": "I'll check."},
            {"kind": "tool", "id": "dom-tool-0"},
            {"kind": "text", "id": "text-1", "text": "Found it."},
        ],
    })
    assert store.write("run", "123:owner", after, now=4)
    detail = store.detail("run")
    assert detail is not None
    assert detail["display_blocks"] == list(after.display_blocks)
    turns = ManualReplyStore(tmp_path / "results.db").turns("run")
    assert turns is not None
    assert turns[0]["display_blocks"] == detail["display_blocks"]


def test_shorter_dom_hydration_never_erases_earlier_commentary() -> None:
    first = ({"kind": "text", "id": "text-0", "text": "I'll check the file first."},)
    stored = merge_display_blocks("[]", first)
    after = merge_display_blocks(stored, ({"kind": "text", "id": "text-0", "text": "I'll"},))
    assert deserialize_display_blocks(after) == list(first)


def test_hidden_thoughts_and_malformed_blocks_are_never_persisted() -> None:
    capture = normalize_dom_snapshot({
        "message_id": "owned-turn", "text": "Visible",
        "display_blocks": [
            {"kind": "text", "id": "text-0", "text": "Visible"},
            {"kind": "analysis", "id": "text-1", "text": "Secret"},
            {"kind": "text", "id": "injected", "text": "Secret"},
        ],
    })
    assert capture.display_blocks == ({"kind": "text", "id": "text-0", "text": "Visible"},)
    assert "Secret" not in str(capture)
