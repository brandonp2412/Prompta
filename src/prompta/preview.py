from __future__ import annotations

import re
from typing import Any

from .ui_noise import is_assistant_ui_noise

SIDEBAR_PREVIEW_LIMIT = 1024
_TOOL_BLOCK_RE = re.compile(
    r"^ {0,3}```(?:tool|tool-call|function|function-call)(?::[^\n\x60]*)?\r?\n"
    r"[\s\S]*?^ {0,3}```[ \t]*\r?$",
    re.IGNORECASE | re.MULTILINE,
)


def compact_sidebar_preview(value: Any) -> str:
    compact = " ".join(_TOOL_BLOCK_RE.sub(" ", str(value or "")).split())
    if is_assistant_ui_noise(compact):
        return ""
    return compact[:SIDEBAR_PREVIEW_LIMIT]
