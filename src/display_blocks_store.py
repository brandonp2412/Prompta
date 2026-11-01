"""Bounded, user-visible transcript blocks, with monotonic snapshot merging."""

from __future__ import annotations

import json
import re

_MAX_BLOCKS = 256
_MAX_CHARS = 2 * 1024 * 1024
_ID_PATTERN = re.compile(r"^(?:text|dom-tool)-[0-9]{1,3}$")


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
        if (kind not in ("text", "tool") or not isinstance(identity, str)
                or not _ID_PATTERN.fullmatch(identity)):
            continue
        if kind == "tool":
            if not identity.startswith("dom-tool-"):
                continue
            items.append({"kind": "tool", "id": identity})
            continue
        raw_text = candidate.get("text")
        if not identity.startswith("text-") or not isinstance(raw_text, str):
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


def merge_display_blocks(previous: object, incoming: tuple[dict[str, str], ...]) -> str:
    if not incoming:
        return previous if isinstance(previous, str) else "[]"
    merged = deserialize_display_blocks(previous)
    positions = {block["id"]: index for index, block in enumerate(merged)}
    for block in incoming:
        identity = block["id"]
        if identity in positions:
            earlier = merged[positions[identity]]
            if (block["kind"] == earlier["kind"] == "text"
                    and len(block["text"]) >= len(earlier["text"])):
                merged[positions[identity]] = block
        elif len(merged) < _MAX_BLOCKS:
            positions[identity] = len(merged)
            merged.append(block)
    return json.dumps(list(normalize_display_blocks(merged)), ensure_ascii=False)
