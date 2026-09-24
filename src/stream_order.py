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


def _prose_extension(previous: _Block, incoming: _Block) -> str:
    """Return only prose newly appended to a matching streaming block."""

    old = previous.normalized
    new = incoming.normalized
    raw = incoming.content.strip()
    if not old or len(new) <= len(old) or not new.startswith(old):
        return ""

    target_index = 0
    for raw_index, char in enumerate(raw):
        if char.isspace():
            if target_index < len(old) and old[target_index] == " ":
                target_index += 1
            continue
        if target_index >= len(old) or char != old[target_index]:
            return ""
        target_index += 1
        if target_index == len(old):
            return raw[raw_index + 1 :].strip()
    return ""


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
    novel: list[tuple[int, _Block]] = []
    search_from = 0

    for old_index, old in enumerate(old_blocks):
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
            continue

        candidate_grew = len(candidate.normalized) > len(old.normalized)
        has_later_tool = any(block.is_tool for block in old_blocks[old_index + 1 :])
        if candidate_grew and has_later_tool:
            stable.append(old)
            extension = _prose_extension(old, candidate)
            if extension:
                novel.append((match_index, _Block(content=extension, is_tool=False)))
            continue

        stable.append(candidate if len(candidate.normalized) >= len(old.normalized) else old)

    novel.extend(
        (index, block) for index, block in enumerate(new_blocks) if index not in matched_new
    )
    novel.sort(key=lambda item: item[0])
    stable.extend(block for _, block in novel)
    return "\n\n".join(block.content.strip() for block in stable if block.content.strip()).strip()


_TRANSIENT_ACTIVITY = {
    "**Tool activity**",
    "Thinking",
}


def _is_transient_activity(block: _Block) -> bool:
    return block.normalized in _TRANSIENT_ACTIVITY


def _collapsed_observation_blocks(content: str) -> list[_Block]:
    collapsed: list[_Block] = []
    for block in _split_prose(content):
        if collapsed and _prose_matches(collapsed[-1], block):
            if len(block.normalized) >= len(collapsed[-1].normalized):
                collapsed[-1] = block
            continue
        collapsed.append(block)
    return collapsed


def compact_prose_observation(content: str) -> str:
    """Collapse adjacent partial copies in one cumulative DOM prose observation."""

    return "\n\n".join(
        block.content.strip()
        for block in _collapsed_observation_blocks(content)
        if block.content.strip()
    ).strip()


def observed_prose_blocks(
    observations: list[tuple[float, str]],
) -> list[tuple[float, str]]:
    """Return final cumulative prose blocks paired with their first-seen time."""

    if not observations:
        return []
    latest_content = observations[-1][1]
    blocks = _collapsed_observation_blocks(latest_content)
    result: list[tuple[float, str]] = []
    for block in blocks:
        if _is_transient_activity(block):
            continue
        first_seen = _observed_at(block, observations)
        if first_seen is None:
            first_seen = observations[-1][0]
        result.append((first_seen, block.content.strip()))
    return result


def _observed_at(block: _Block, observations: list[tuple[float, str]]) -> float | None:
    if block.is_tool:
        if not block.created_at:
            return None
        try:
            value = float(block.created_at)
        except ValueError:
            return None
        return value if value > 0 else None

    for observed_at, content in observations:
        for observed in _collapsed_observation_blocks(content):
            if _prose_matches(observed, block):
                return observed_at
    return None


def has_stream_order_inversion(
    content: str,
    observations: list[tuple[float, str]],
) -> bool:
    """Return whether known first-seen times disagree with current block order."""

    last_time: float | None = None
    for block in _split_stream_blocks(content):
        if _is_transient_activity(block):
            continue
        current_time = _observed_at(block, observations)
        if current_time is None:
            continue
        if last_time is not None and current_time < last_time:
            return True
        last_time = current_time
    return False


def recover_stream_order_from_observations(
    content: str,
    observations: list[tuple[float, str]],
) -> str:
    """Reorder a corrupted stream using persisted first-seen prose/tool times."""

    blocks = [block for block in _split_stream_blocks(content) if not _is_transient_activity(block)]
    timed = [
        (_observed_at(block, observations), index, block) for index, block in enumerate(blocks)
    ]
    timed.sort(
        key=lambda item: (
            item[0] if item[0] is not None else float("inf"),
            item[1],
        )
    )
    return "\n\n".join(
        block.content.strip() for _, _, block in timed if block.content.strip()
    ).strip()
