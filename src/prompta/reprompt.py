from __future__ import annotations

from typing import Any

REPROMPT_TEXT = "Continue"
_UNFINISHED_TERMINALS = {
    "work remains",
    "still running",
    "task remains",
    "not yet done",
}
_MARKDOWN_EDGE_CHARS = " \t*_>#-.!;:\"'"


def _normalise_prompt(text: str) -> str:
    return " ".join(text.split()).casefold()


def reprompt_streak(messages: list[dict[str, Any]]) -> int:
    """Count trailing automatic Continue turns since the last substantive user prompt."""

    count = 0
    for message in reversed(messages):
        if str(message.get("role") or "") != "user":
            continue
        content = _normalise_prompt(str(message.get("content") or ""))
        if content == REPROMPT_TEXT.casefold():
            count += 1
            continue
        break
    return count


def unfinished_reply(messages: list[dict[str, Any]]) -> bool:
    """Return whether the latest assistant turn explicitly says work remains."""

    assistant = next(
        (
            message
            for message in reversed(messages)
            if str(message.get("role") or "") == "assistant"
        ),
        None,
    )
    if assistant is None:
        return False
    lines = [line for line in str(assistant.get("content") or "").splitlines() if line.strip()]
    if not lines:
        return False
    terminal = lines[-1].casefold().strip(_MARKDOWN_EDGE_CHARS)
    return terminal in _UNFINISHED_TERMINALS
