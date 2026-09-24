from __future__ import annotations

import json
from typing import Any

from .browser_script_loader import load_browser_script
from .chatgpt_dom import (
    LEGACY_RICH_TEXT_SELECTOR,
    PROSE_BLOCK_SELECTOR,
    STOP_BUTTON_SELECTOR,
    STREAMING_SELECTOR,
)
from .transcript_browser_engine import TRANSCRIPT_BROWSER_ENGINE_SCRIPT

CONVERSATION_SNAPSHOT_SCRIPT = load_browser_script("conversation_snapshot.js")

CONVERSATION_SNAPSHOT_SCRIPT = (
    CONVERSATION_SNAPSHOT_SCRIPT.replace(
        "/*__TRANSCRIPT_BROWSER_ENGINE__*/", TRANSCRIPT_BROWSER_ENGINE_SCRIPT
    )
    .replace("__PROSE_BLOCK_SELECTOR__", json.dumps(PROSE_BLOCK_SELECTOR))
    .replace("__LEGACY_RICH_TEXT_SELECTOR__", json.dumps(LEGACY_RICH_TEXT_SELECTOR))
    .replace("__STOP_SELECTOR__", json.dumps(STOP_BUTTON_SELECTOR))
    .replace("__STREAMING_SELECTOR__", json.dumps(STREAMING_SELECTOR))
)


def parse_conversation_snapshot(raw: str) -> dict[str, Any]:
    return json.loads(raw or "{}")
