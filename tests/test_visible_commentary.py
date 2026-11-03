"""Visible commentary remains distinct and ordered across capture, SQLite and replies."""

from pathlib import Path

from prompta.delivery_browser import _retain_dom_progress
from prompta.display_blocks_store import (
    deserialize_display_blocks,
    display_blocks_text,
    merge_display_blocks,
    visible_assistant_text,
)
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
    assert detail["display_blocks"] == [
        {"kind": "text", "id": "text-0", "text": "I'll check."},
        {"kind": "tool", "id": "dom-tool-0"},
        {"kind": "text", "id": "text-1", "text": "Found it."},
    ]
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


def test_final_dom_collapse_does_not_overwrite_opening_and_middle(tmp_path: Path) -> None:
    """Live ChatGPT can replace the progress DOM with a final-only text-0."""
    store = ResponseStore(tmp_path / "results.db")
    store.ensure_queued("run", "Commentary canary", now=1)
    assert store.accept("run", "123:owner", deadline=100, now=2)
    base = {
        "message_id": "fallback-turn-0",
        "branch_message_id": "59188b32-a6b2-5b6d-9f58-59ed1ebaba53",
        "pathname": "/c/12345678-1234-4123-8123-123456789abc",
    }
    progress = normalize_dom_snapshot({**base, "text": "OPENING\n\nMIDDLE", "display_blocks": [
        {"kind": "text", "id": "text-0", "text": "OPENING"},
        {"kind": "tool", "id": "dom-tool-0"},
        {"kind": "text", "id": "text-1", "text": "MIDDLE"},
    ]})
    assert store.write("run", "123:owner", progress, now=3)
    # The final ChatGPT frame drops commentary and renumbers its answer text-0.
    final = normalize_dom_snapshot({**base, "text": "FINISH — 2022", "complete": True,
        "display_blocks": [{"kind": "text", "id": "text-0", "text": "FINISH — 2022"}],
    })
    assert store.write("run", "123:owner", final, now=4)
    detail = store.detail("run")
    assert detail is not None and detail["status"] == "completed"
    assert detail["assistant_text"] == "OPENING\n\nMIDDLE\n\nFINISH — 2022"
    assert detail["display_blocks"] == [
        {"kind": "text", "id": "text-0", "text": "OPENING"},
        {"kind": "tool", "id": "dom-tool-0"},
        {"kind": "text", "id": "text-1", "text": "MIDDLE"},
        {"kind": "text", "id": "text-2", "text": "FINISH — 2022"},
    ]


def test_reindexed_streaming_text_grows_in_place_without_duplicates() -> None:
    saved = merge_display_blocks("[]", (
        {"kind": "text", "id": "text-0", "text": "OPENING"},
    ))
    saved = merge_display_blocks(saved, (
        {"kind": "text", "id": "text-0", "text": "MIDDLE sta"},
    ))
    saved = merge_display_blocks(saved, (
        {"kind": "text", "id": "text-0", "text": "MIDDLE stage complete"},
    ))
    saved = merge_display_blocks(saved, (
        {"kind": "text", "id": "text-0", "text": "MIDDLE stage complete"},
    ))
    assert deserialize_display_blocks(saved) == [
        {"kind": "text", "id": "text-0", "text": "OPENING"},
        {"kind": "text", "id": "text-1", "text": "MIDDLE stage complete"},
    ]


def test_intermediate_dom_frames_survive_between_database_writes() -> None:
    """A fast tool continuation may finish before the next SQLite flush."""
    saved = "[]"
    payloads = (
        {"message_id": "owned-turn", "text": "OPENING", "display_blocks": [
            {"kind": "text", "id": "text-0", "text": "OPENING"},
        ]},
        {"message_id": "owned-turn", "text": "MIDDLE", "display_blocks": [
            {"kind": "tool", "id": "dom-tool-0"},
            {"kind": "text", "id": "text-0", "text": "MIDDLE"},
        ]},
        {"message_id": "owned-turn", "text": "FINISH", "complete": True,
         "display_blocks": [{"kind": "text", "id": "text-0", "text": "FINISH"}]},
    )
    final = normalize_dom_snapshot(payloads[0])
    for payload in payloads:
        saved, final = _retain_dom_progress(saved, normalize_dom_snapshot(payload))
    assert final.text == "OPENING\n\nMIDDLE\n\nFINISH"
    assert final.display_blocks == (
        {"kind": "text", "id": "text-0", "text": "OPENING"},
        {"kind": "tool", "id": "dom-tool-0"},
        {"kind": "text", "id": "text-1", "text": "MIDDLE"},
        {"kind": "text", "id": "text-2", "text": "FINISH"},
    )
    assert final.status == "complete"


def test_growing_markdown_table_replaces_partial_versions_even_when_links_change() -> None:
    """The reported live chat emitted a new text-N for every partial table."""
    opening = "Checking repository popularity."
    prefix = (
        "## Selected projects\n\nI identified the six most-starred, unarchived "
        "Android repositories that need an upgrade and F-Droid verification.\n\n"
        "| Project | Stars | Upgrade scope |\n|---|---:|---|\n"
    )
    partial = prefix + "| [Flex](https://github.com/brandonp](https://github.com/brandonp?utm_source=chatgpt.com) |  |  |"
    refined = prefix + "| [Flex](https://github.com/brandonp2412/Flex) | 454 | Flutter |\n| Quitter | 198 | Flutter |"
    finished = refined + "\n| FitBook | 177 | Flutter |\n\nAll 6 jobs queued."
    saved = merge_display_blocks("[]", (
        {"kind": "text", "id": "text-0", "text": opening},
        {"kind": "tool", "id": "dom-tool-0"},
        {"kind": "text", "id": "text-1", "text": partial},
    ))
    saved = merge_display_blocks(saved, (
        {"kind": "text", "id": "text-0", "text": opening},
        {"kind": "tool", "id": "dom-tool-0"},
        {"kind": "text", "id": "text-1", "text": refined},
    ))
    saved = merge_display_blocks(saved, (
        {"kind": "text", "id": "text-0", "text": opening},
        {"kind": "tool", "id": "dom-tool-0"},
        {"kind": "text", "id": "text-1", "text": finished},
    ))
    blocks = deserialize_display_blocks(saved)
    assert [block["kind"] for block in blocks] == ["text", "tool", "text"]
    assert display_blocks_text(saved) == opening + "\n\n" + finished
    assert display_blocks_text(saved).count("## Selected projects") == 1
    # An earlier shortened frame never rolls back a completed answer.
    assert merge_display_blocks(saved, (
        {"kind": "text", "id": "text-0", "text": partial},
    )) == saved


def test_legacy_cumulative_transcript_reads_as_one_answer() -> None:
    """Existing SQLite rows and copied replies must not show the partial table six times."""
    import json

    prefix = "## Selected projects\n\n" + "I identified the six projects. " * 8
    versions = (
        prefix + "\n| Flex | 454 |",
        prefix + "\n| Flex | 454 |\n| Quitter | 198 |",
        prefix + "\n| Flex | 454 |\n| Quitter | 198 |\n| FitBook | 177 |",
    )
    raw_blocks = [
        {"kind": "text", "id": "text-0", "text": "I'll check first."},
        *({"kind": "text", "id": f"text-{i + 1}", "text": version}
          for i, version in enumerate(versions)),
    ]
    raw_json = json.dumps(raw_blocks)
    duplicated = "\n\n".join(block["text"] for block in raw_blocks)
    expected = "I'll check first.\n\n" + versions[-1]
    assert visible_assistant_text(duplicated, raw_json) == expected
    assert display_blocks_text(raw_json) == expected
    assert len(deserialize_display_blocks(raw_json)) == 2
    # Text from a different source must never be replaced by a DOM reconstruction.
    assert visible_assistant_text("Independent final SSE answer.", raw_json) == "Independent final SSE answer."


def test_long_repeated_opening_with_different_substance_is_not_collapsed() -> None:
    import json

    lead = "## Migration status\n\n" + "A shared introductory explanation. " * 5
    first = lead + "Alpha " * 90
    second = lead + "Beta " * 90
    blocks = [
        {"kind": "text", "id": "text-0", "text": first},
        {"kind": "text", "id": "text-1", "text": second},
    ]
    assert len(deserialize_display_blocks(json.dumps(blocks))) == 2
