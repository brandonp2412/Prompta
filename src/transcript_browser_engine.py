"""Shared browser-side transcript extraction engine."""

from __future__ import annotations

from importlib.resources import files

from .chatgpt_dom import MESSAGE_DISCOVERY_SCRIPT
from .react_fallback import REACT_FALLBACK_ADAPTER_SCRIPT

_ENGINE_TEMPLATE = (
    files("prompta").joinpath("browser_transcript_engine.js").read_text(encoding="utf-8")
)

TRANSCRIPT_BROWSER_ENGINE_SCRIPT = _ENGINE_TEMPLATE.replace(
    "__MESSAGE_DISCOVERY__", MESSAGE_DISCOVERY_SCRIPT
).replace("__REACT_FALLBACK_ADAPTER__", REACT_FALLBACK_ADAPTER_SCRIPT)
