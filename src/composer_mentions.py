"""Translate Prompta @tokens to the native ChatGPT composer selections."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class NativeMention:
    name: str
    kind: str


def _catalog() -> tuple[NativeMention, ...]:
    path = Path(__file__).parent / "static" / "mention-catalog.json"
    raw: object = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError("Invalid mention catalog")
    entries: list[NativeMention] = []
    for entry in raw:
        if not isinstance(entry, dict):
            raise ValueError("Invalid mention catalog entry")
        name = entry.get("name")
        kind = entry.get("kind")
        if not isinstance(name, str) or not isinstance(kind, str):
            raise ValueError("Invalid mention catalog entry")
        entries.append(NativeMention(name, kind))
    return tuple(entries)


MENTIONS = _catalog()
_MENTION_BY_NAME = {mention.name.casefold(): mention for mention in MENTIONS}
_MENTION_PATTERN = re.compile(
    r"(?<![\w@])@("
    + "|".join(re.escape(name) for name in sorted(
        (mention.name for mention in MENTIONS),
        key=len,
        reverse=True,
    ))
    + r")(?=$|[\s.,!?;:)\]}])",
    re.IGNORECASE,
)


def split_native_mentions(text: str) -> list[str | NativeMention]:
    """Preserve prose verbatim; convert only known, delimited @mentions."""
    parts: list[str | NativeMention] = []
    start = 0
    for match in _MENTION_PATTERN.finditer(text):
        if match.start() > start:
            parts.append(text[start:match.start()])
        parts.append(_MENTION_BY_NAME[match.group(1).casefold()])
        start = match.end()
    if start < len(text):
        parts.append(text[start:])
    return parts or [text]


def expected_native_text(parts: list[str | NativeMention]) -> str:
    return "".join(part if isinstance(part, str) else part.name + " " for part in parts)
