from __future__ import annotations

import json
from typing import Any

from .browser_script_loader import render_browser_script
from .chatgpt_dom import (
    ASSISTANT_MESSAGE_SELECTOR,
    MARKDOWN_SELECTOR,
    MESSAGE_ROLE_SELECTOR,
    STOP_BUTTON_SELECTOR,
    STREAMING_SELECTOR,
    TURN_SELECTOR,
)

CONVERSATION_SNAPSHOT_SCRIPT = render_browser_script(
    "conversation_snapshot.js",
    MESSAGE_ROLE_SELECTOR=MESSAGE_ROLE_SELECTOR,
    ASSISTANT_SELECTOR=ASSISTANT_MESSAGE_SELECTOR,
    TURN_SELECTOR=TURN_SELECTOR,
    MARKDOWN_SELECTOR=MARKDOWN_SELECTOR,
    STOP_SELECTOR=STOP_BUTTON_SELECTOR,
    STREAMING_SELECTOR=STREAMING_SELECTOR,
)


def parse_conversation_snapshot(raw: str) -> dict[str, Any]:
    return json.loads(raw or "{}")
