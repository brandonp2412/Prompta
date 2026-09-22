"""Stable ordering helpers for live assistant message content."""

from __future__ import annotations

import re
from dataclasses import dataclass

_FENCE = chr(96) * 3
_TOOL_PREFIX = f"{_FENCE}tool:"
_BLANK_LINES = re.compile(r"\n[ \t]*\n+")
_CREATED_AT = re.compile(r'"created_at"\s*:\s*(-?\d+(?:\.\d+)?)')


@dataclass(frozen=True)
class _Block:
    content: str
    is_tool: bool
    tool_title: str = ""
    created_at: str = ""

    @property
    def normalized(self) -> str:
        return " ".join(self.content.split())


def _tool_identity(content: str) -> tuple[str, str]:
    lines = content.splitlines()
    title = lines[0].strip() if lines else ""
    match = _CREATED_AT.search(content)
    return title, match.group(1) if match else ""


def _split_prose(content: str) -> list[_Block]:
    return [
        _Block(content=part.strip(), is_tool=False)
        for part in _BLANK_LINES.split(content.strip())
        if part.strip()
    ]


def _split_stream_blocks(content: str) -> list[_Block]:
    """Split rendered assistant content without breaking fenced tool payloads."""

    text = content.strip()
    if not text:
        return []

    blocks: list[_Block] = []
    prose_start = 0
    cursor = 0
    while True:
        tool_start = text.find(_TOOL_PREFIX, cursor)
        if tool_start < 0:
            break
        if tool_start > prose_start:
            blocks.extend(_split_prose(text[prose_start:tool_start]))
        closing_marker = chr(10) + _FENCE
        fence_end = text.find(closing_marker, tool_start + len(_TOOL_PREFIX))
        if fence_end < 0:
            blocks.extend(_split_prose(text[tool_start:]))
            return blocks
        tool_end = fence_end + len(closing_marker)
        tool_content = text[tool_start:tool_end].strip()
        title, created_at = _tool_identity(tool_content)
        blocks.append(
            _Block(
                content=tool_content,
                is_tool=True,
                tool_title=title,
                created_at=created_at,
            )
        )
        cursor = tool_end
        prose_start = cursor

    if prose_start < len(text):
        blocks.extend(_split_prose(text[prose_start:]))
    return blocks


def _tool_matches(previous: _Block, incoming: _Block) -> bool:
    if not previous.is_tool or not incoming.is_tool:
        return False
    if previous.tool_title != incoming.tool_title:
        return False
    if previous.created_at and incoming.created_at:
        return previous.created_at == incoming.created_at
    return previous.normalized == incoming.normalized


def _prose_matches(previous: _Block, incoming: _Block) -> bool:
    if previous.is_tool or incoming.is_tool:
        return False
    old = previous.normalized
    new = incoming.normalized
    if not old or not new:
        return False
    return old == new or new.startswith(old) or old.startswith(new)


def _matches(previous: _Block, incoming: _Block) -> bool:
    return (
        _tool_matches(previous, incoming)
        if previous.is_tool
        else _prose_matches(previous, incoming)
    )


def stabilize_streaming_content(previous: str, incoming: str) -> str:
    """Keep already-visible blocks in place while accepting live updates."""

    old_blocks = _split_stream_blocks(previous)
    new_blocks = _split_stream_blocks(incoming)
    if not old_blocks:
        return incoming.strip()
    if not new_blocks:
        return previous.strip()

    matched_new: set[int] = set()
    stable: list[_Block] = []
    search_from = 0

    for old in old_blocks:
        match_index = -1
        for index in range(search_from, len(new_blocks)):
            if index not in matched_new and _matches(old, new_blocks[index]):
                match_index = index
                break
        if match_index < 0:
            for index, candidate in enumerate(new_blocks):
                if index not in matched_new and _matches(old, candidate):
                    match_index = index
                    break

        if match_index < 0:
            stable.append(old)
            continue

        candidate = new_blocks[match_index]
        matched_new.add(match_index)
        search_from = match_index + 1

        if old.is_tool:
            stable.append(candidate)
        else:
            stable.append(candidate if len(candidate.normalized) >= len(old.normalized) else old)

    stable.extend(block for index, block in enumerate(new_blocks) if index not in matched_new)
    return "\n\n".join(block.content.strip() for block in stable if block.content.strip()).strip()


def recover_streaming_content(history: list[str], incoming: str) -> str:
    """Replay historical snapshots to recover first-seen block order."""

    stable = ""
    for content in [*history, incoming]:
        if not content or not content.strip():
            continue
        stable = stabilize_streaming_content(stable, content)
    return stable
