"""Explicit adapter for optional React-private transcript introspection."""

from __future__ import annotations

from typing import Any, Literal, TypedDict

from .browser_script_loader import load_browser_script

ReactFallbackProvenance = Literal["react-private-properties"]


class ReactFallbackResult(TypedDict):
    """Structured result returned by the browser-side React fallback adapter."""

    allowed: bool
    used: bool
    available: bool
    provenance: ReactFallbackProvenance
    reason: str
    property_names: list[str]
    messages: list[dict[str, Any]]
    truncated: bool
    scanned_nodes: int
    scanned_objects: int
    error: str


REACT_FALLBACK_ADAPTER_SCRIPT = load_browser_script("react_fallback_adapter.js")
