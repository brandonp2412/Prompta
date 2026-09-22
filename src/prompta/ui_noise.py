from __future__ import annotations

import re
from typing import Any

_NETWORK_ERROR_RE = re.compile(
    r"a network error occurred\.?\s*"
    r"please check your connection and try again\.?\s*"
    r"if this issue persists please contact us through our help center at help\.openai\.com\.?",
    re.IGNORECASE,
)
_ASSISTANT_UI_NOISE_RE = re.compile(
    r"(?:"
    r"connection interrupted\.?|"
    r"waiting for the complete answer|"
    r"message delivery timed out\.?\s*please try again\.?|"
    r"a network error occurred\.?\s*"
    r"please check your connection and try again\.?\s*"
    r"if this issue persists please contact us through our help center at help\.openai\.com\.?"
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
