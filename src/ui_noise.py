from __future__ import annotations

import re
from typing import Any

_HELP_CENTER_TARGET_RE = (
    r"(?:help\.openai\.com|\[help\.openai\.com\]\(https?://help\.openai\.com/?\))"
)

_NETWORK_ERROR_RE = re.compile(
    r"a network error occurred\.?\s*"
    r"please check your connection and try again\.?\s*"
    r"if this issue persists please contact us through our help center at "
    + _HELP_CENTER_TARGET_RE
    + r"\.?",
    re.IGNORECASE,
)
_ASSISTANT_UI_NOISE_RE = re.compile(
    r"(?:"
    r"(?:#{1,6}\s*)?chatgpt said:?|"
    r"connection interrupted\.?(?:\s*waiting for (?:the )?complete answer\.?)?|"
    r"waiting for (?:the )?complete answer\.?|"
    r"message delivery timed out\.?\s*please try again\.?|"
    r"a network error occurred\.?"
    r"(?:\s*please check your connection and try again\.?"
    r"(?:\s*if this issue persists please contact us through our help center at "
    + _HELP_CENTER_TARGET_RE
    + r"\.?)?"
    r")?"
    r")",
    re.IGNORECASE,
)


def is_assistant_ui_noise(value: Any) -> bool:
    """Return whether value is a known ChatGPT transport/status UI message."""

    compact = " ".join(str(value or "").split())
    return bool(compact and _ASSISTANT_UI_NOISE_RE.fullmatch(compact))


def strip_assistant_ui_noise(value: Any) -> str:
    """Remove known ChatGPT transport/status UI text from captured transcript content."""

    text = _NETWORK_ERROR_RE.sub("", str(value or ""))
    return "\n".join(line for line in text.splitlines() if not is_assistant_ui_noise(line)).strip()
