"""Bounded, user-visible transcript blocks, with monotonic snapshot merging."""

from __future__ import annotations

import json
import re

_MAX_BLOCKS = 256
_MAX_CHARS = 2 * 1024 * 1024
_ID_PATTERN = re.compile(r"^(?:(?:text|dom-tool)-[0-9]{1,3}|sse-(?:text|tool)-[0-9a-f]{24})$")
_CALL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")


def normalize_display_blocks(value: object) -> tuple[dict[str, str], ...]:
    if not isinstance(value, list):
        return ()
    items: list[dict[str, str]] = []
    length = 0
    for candidate in value[:_MAX_BLOCKS]:
        if not isinstance(candidate, dict):
            continue
        kind = candidate.get("kind")
        identity = candidate.get("id")
        if (
            kind not in ("text", "tool")
            or not isinstance(identity, str)
            or not _ID_PATTERN.fullmatch(identity)
        ):
            continue
        if kind == "tool":
            if identity.startswith("dom-tool-"):
                items.append({"kind": "tool", "id": identity})
            elif identity.startswith("sse-tool-"):
                tool_id = candidate.get("tool_id")
                if isinstance(tool_id, str) and _CALL_ID_PATTERN.fullmatch(tool_id):
                    items.append({"kind": "tool", "id": identity, "tool_id": tool_id})
            continue
        raw_text = candidate.get("text")
        if not identity.startswith(("text-", "sse-text-")) or not isinstance(raw_text, str):
            continue
        text = raw_text.strip()
        if not text or length + len(text) > _MAX_CHARS:
            continue
        length += len(text)
        items.append({"kind": "text", "id": identity, "text": text})
    return tuple(items)


def deserialize_display_blocks(value: object) -> list[dict[str, str]]:
    if not isinstance(value, str):
        return []
    try:
        parsed: object = json.loads(value)
    except (TypeError, ValueError):
        return []
    return list(normalize_display_blocks(parsed))


def display_blocks_text(value: object) -> str:
    """User-visible Markdown prose in the same order as retained tool markers."""
    return "\n\n".join(
        block["text"] for block in deserialize_display_blocks(value) if block["kind"] == "text"
    )[:_MAX_CHARS]


def merge_display_blocks(previous: object, incoming: tuple[dict[str, str], ...]) -> str:
    """Keep progress that disappeared from a final ChatGPT DOM snapshot.

    ChatGPT can collapse opening/intermediate commentary when its final answer
    replaces the activity view. The new snapshot then starts again at text-0;
    those IDs are positional, not stable message identities. Match prose by
    content before IDs, and only grow a block when the new text extends it.
    """
    if not incoming:
        return previous if isinstance(previous, str) else "[]"
    merged = deserialize_display_blocks(previous)
    matched: set[int] = set()
    for block in normalize_display_blocks(list(incoming)):
        identity = block["id"]
        kind = block["kind"]
        stable = identity.startswith("sse-")
        if kind == "tool":
            index = next(
                (
                    i
                    for i, prior in enumerate(merged)
                    if prior["id"] == identity and prior["kind"] == "tool"
                ),
                None,
            )
            if index is not None:
                matched.add(index)
                continue
        else:
            incoming_text = block["text"]
            stable_index = (
                next(
                    (
                        i
                        for i, prior in enumerate(merged)
                        if prior["id"] == identity and prior["kind"] == "text"
                    ),
                    None,
                )
                if stable
                else None
            )
            candidates = [
                (i, prior["text"])
                for i, prior in enumerate(merged)
                if i not in matched
                and prior["kind"] == "text"
                and (not stable or not prior["id"].startswith("sse-"))
            ]
            exact = next((i for i, text in candidates if text == incoming_text), None)
            growing = max(
                ((len(text), i) for i, text in candidates if incoming_text.startswith(text)),
                default=None,
            )
            shrinking = max(
                (
                    (len(incoming_text), i)
                    for i, text in candidates
                    if text.startswith(incoming_text)
                ),
                default=None,
            )
            index = (
                stable_index
                if stable_index is not None
                else (
                    exact
                    if exact is not None
                    else (
                        growing[1]
                        if growing is not None
                        else (shrinking[1] if shrinking is not None else None)
                    )
                )
            )
            if index is not None:
                matched.add(index)
                if len(incoming_text) >= len(merged[index]["text"]):
                    merged[index] = {**block, "id": merged[index]["id"]}
                continue
        if len(merged) >= _MAX_BLOCKS:
            continue
        used = {existing["id"] for existing in merged}
        if identity in used:
            prefix = "text" if kind == "text" else "dom-tool"
            identity = next(
                f"{prefix}-{i}" for i in range(_MAX_BLOCKS) if f"{prefix}-{i}" not in used
            )
        matched.add(len(merged))
        merged.append({**block, "id": identity})
    return json.dumps(list(normalize_display_blocks(merged)), ensure_ascii=False)
