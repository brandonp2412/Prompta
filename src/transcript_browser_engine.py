"""Shared browser-side transcript extraction engine."""

from __future__ import annotations

from .browser_script_loader import load_browser_script
from .chatgpt_dom import MESSAGE_DISCOVERY_SCRIPT
from .react_fallback import REACT_FALLBACK_ADAPTER_SCRIPT

_ENGINE_TEMPLATE = load_browser_script("transcript_browser_engine.js")

TRANSCRIPT_BROWSER_ENGINE_SCRIPT = _ENGINE_TEMPLATE.replace(
    "/*__MESSAGE_DISCOVERY__*/", MESSAGE_DISCOVERY_SCRIPT
).replace("/*__REACT_FALLBACK_ADAPTER__*/", REACT_FALLBACK_ADAPTER_SCRIPT)
