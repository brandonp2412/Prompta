"""Bounded, user-visible transcript blocks, with monotonic snapshot merging."""

from __future__ import annotations

import json
import re
from difflib import SequenceMatcher

_MAX_BLOCKS = 256
_MAX_CHARS = 2 * 1024 * 1024
_ID_PATTERN = re.compile(r"^(?:(?:text|dom-tool)-[0-9]{1,3}|sse-(?:text|tool)-[0-9a-f]{24})$")
_CALL_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]{1,100}$")
_SEEN_AT_PATTERN = re.compile(r"^\d{10}(?:\.\d{1,6})?$")


def _progressive_versions(first: str, second: str) -> bool:
    """Recognize a Markdown block re-rendered while it is still streaming.

    The DOM observer can give successive versions of one growing table new
    positional IDs. Markdown links may be repaired between frames, so a strict
    startswith comparison is insufficient. Restrict fuzzy matching to a long,
    identical opening and a bounded, substantially similar prefix.
    """
    shorter, longer = sorted((first, second), key=len)
    if len(shorter) < 160 or shorter[:96] != longer[:96]:
        return False
    sample = shorter[:512]
    return SequenceMatcher(None, sample, longer[: len(sample) + 64], autojunk=False).ratio() >= 0.75


def _collapse_progressive_versions(items: list[dict[str, str]]) -> tuple[dict[str, str], ...]:
    visible: list[dict[str, str]] = []
    for block in items:
        if block["kind"] != "text":
            visible.append(block)
            continue
        matches = [
            index for index, prior in enumerate(visible)
            if prior["kind"] == "text" and _progressive_versions(prior["text"], block["text"])
        ]
        if not matches:
            visible.append(block)
            continue
        best = max((visible[index] for index in matches), key=lambda item: len(item["text"]))
        # A truncated hydration frame must not replace a longer verified one.
        # A re-rendered earlier commentary block stays at its first position;
        # moving it after intervening calls reverses the actual chronology.
        if len(block["text"]) <= len(best["text"]):
            continue
        first = min(matches)
        original = visible[first]
        replacement = {**block, "id": original["id"]}
        if "seen_at" in original:
            replacement["seen_at"] = original["seen_at"]
        for index in reversed(matches):
            del visible[index]
        visible.insert(first, replacement)
    return tuple(visible)


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
        seen_at = candidate.get("seen_at")
        timing = (
            {"seen_at": seen_at}
            if isinstance(seen_at, str) and _SEEN_AT_PATTERN.fullmatch(seen_at)
            else {}
        )
        items.append({"kind": "text", "id": identity, "text": text, **timing})
    return _collapse_progressive_versions(items)


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


def visible_assistant_text(saved_text: str, blocks_json: object) -> str:
    """Read legacy duplicated transcripts without rewriting historical rows.

    Only substitute the cleaned blocks when the saved text is exactly their
    original concatenation. Keep independent SSE text or missing DOM prose.
    """
    if not isinstance(blocks_json, str):
        return saved_text
    try:
        raw: object = json.loads(blocks_json)
    except (TypeError, ValueError):
        return saved_text
    if not isinstance(raw, list):
        return saved_text
    text_blocks: list[str] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        candidate = item.get("text")
        if item.get("kind") == "text" and isinstance(candidate, str):
            text_blocks.append(candidate.strip())
    unmerged = "\n\n".join(text_blocks)
    compact = display_blocks_text(blocks_json)
    return compact if len(compact) < len(unmerged) and saved_text.strip() == unmerged else saved_text


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
                    old = merged[index]
                    merged[index] = {**block, "id": old["id"]}
                    if "seen_at" in old:
                        merged[index]["seen_at"] = old["seen_at"]
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
