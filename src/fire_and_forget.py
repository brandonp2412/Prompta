"""Production switch for send-only Prompta operation.

Local database reads still power scheduling and the UI. ChatGPT response/history
reads and reply recovery are disabled while this switch is enabled.
"""

from __future__ import annotations

import os


def enabled() -> bool:
    return os.environ.get("PROMPTA_FIRE_AND_FORGET", "0") == "1"
