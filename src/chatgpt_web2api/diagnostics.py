"""Reactive diagnostics: detect broken driver calls + capture evidence.

When ChatGPT changes its API/UI, driver methods silently return wrong shapes.
This module classifies results against an expected-shape registry so breakage
is caught at the moment it happens, then (in later tasks) captures the evidence.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

# Expected shape per driver method. Each entry is a dict with:
#   kind: "list" | "dict" | "bool" | "any"
#   required_keys / item_required_keys: list[str]
EXPECTED_SHAPES: dict[str, dict] = {
    "get_models": {"kind": "list", "item_required_keys": ["slug", "title"]},
    "get_projects": {"kind": "list", "item_required_keys": ["id", "name"]},
    "get_conversations": {"kind": "list", "item_required_keys": ["id", "title"]},
    "get_conversation": {"kind": "dict", "required_keys": ["id", "messages"]},
    "get_memories": {"kind": "list", "item_required_keys": ["id", "content"]},
    "list_gpts": {"kind": "list", "item_required_keys": ["id", "name"]},
    "get_project_files": {"kind": "list", "item_required_keys": ["id", "name"]},
    "create_project": {"kind": "dict", "required_keys": ["id", "name"]},
    "update_project_instructions": {"kind": "dict", "required_keys": ["success", "project_id"]},
    "archive_conversation": {"kind": "dict", "required_keys": ["success", "conversation_id"]},
    "delete_conversation": {"kind": "bool"},
    "delete_memory": {"kind": "bool"},
    "create_memory": {"kind": "dict", "required_keys": ["content"]},
}


def classify_result(function_name: str, result: Any) -> tuple[bool, str | None]:
    """Classify a driver method's return as healthy or broken.

    Returns (healthy, mismatch). Broken cases:
      - result is a dict containing an "error" key (explicit API error)
      - result type doesn't match the registered kind
      - a dict result is missing a required key
      - a list result's items are missing item_required_keys
    """
    spec = EXPECTED_SHAPES.get(function_name, {"kind": "any"})

    if isinstance(result, dict) and "error" in result:
        return False, f"returned error shape: {result.get('error', '?')}"

    kind = spec.get("kind", "any")
    if kind == "any":
        return True, None
    if kind == "bool":
        if not isinstance(result, bool):
            return False, f"expected bool, got {type(result).__name__}"
        return True, None
    if kind == "list":
        if not isinstance(result, list):
            return False, f"expected list, got {type(result).__name__}"
        req = spec.get("item_required_keys", [])
        for i, item in enumerate(result[:3]):
            if not isinstance(item, dict):
                return False, f"list item {i} is {type(item).__name__}, not dict"
            missing = [k for k in req if k not in item]
            if missing:
                return False, f"list item {i} missing keys: {missing}"
        return True, None
    if kind == "dict":
        if not isinstance(result, dict):
            return False, f"expected dict, got {type(result).__name__}"
        missing = [k for k in spec.get("required_keys", []) if k not in result]
        if missing:
            return False, f"missing required keys: {missing}"
        return True, None
    return True, None


# ═══════════════════════════════════════════════════════════════
# Artifact capture + redaction
# ═══════════════════════════════════════════════════════════════

# Patterns treated as secrets/PII and redacted whole.
_REDACT_VALUE_PATTERNS = [
    re.compile(r"eyJ[A-Za-z0-9_\.\-]{20,}"),  # JWT-looking tokens
    re.compile(r"__Secure-[A-Za-z0-9_\.\-]+=[A-Za-z0-9_\.\-]{20,}"),  # secure cookies
    re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"),  # emails
]
_REDACT_KEY_HINTS = ("token", "authorization", "cookie", "password", "secret", "email")
_MAX_BODY_CHARS = 2000


def _redact_string(s: str) -> str:
    for pat in _REDACT_VALUE_PATTERNS:
        s = pat.sub("<redacted>", s)
    return s


def redact(obj: Any) -> Any:
    """Recursively redact secrets/PII from a JSON-serializable structure.

    Replaces JWTs, secure-cookie values, and emails anywhere in strings; blanks
    values whose key hints at being a secret; truncates long string values.
    """
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if any(hint in k.lower() for hint in _REDACT_KEY_HINTS):
                out[k] = "<redacted>"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    if isinstance(obj, str):
        if len(obj) <= _MAX_BODY_CHARS:
            return _redact_string(obj)
        # Truncate so the total (body + marker) fits within the cap.
        marker = "...<truncated>"
        return _redact_string(obj[:_MAX_BODY_CHARS - len(marker)] + marker)
    return obj


class DiagnosticsDir:
    """Writes + reads diagnostic artifacts under a base directory."""

    def __init__(self, base: Path | None = None, max_per_function: int = 5) -> None:
        self.base = Path(base) if base else Path.home() / ".chatgpt-web2api" / "diagnostics"
        self.base.mkdir(parents=True, exist_ok=True)
        self.max_per_function = max_per_function
        # Monotonic counter ensures filename sort order always matches creation
        # order, even when multiple captures land in the same wall-clock second.
        self._seq = 0

    def capture(self, *, function: str, request: Any, response: Any,
                expected: Any, actual: Any, mismatch: str) -> Path:
        """Write a redacted artifact and enforce the per-function volume cap."""
        ts = time.strftime("%Y%m%d-%H%M%S")
        self._seq += 1
        # seq is zero-padded so lexical sort == chronological order.
        path = self.base / f"{function}-{ts}-{self._seq:06d}.json"
        payload = redact({
            "function": function,
            "timestamp": ts,
            "request": request,
            "response": response,
            "expected": expected,
            "actual": actual,
            "mismatch": mismatch,
        })
        path.write_text(json.dumps(payload, indent=2, default=str))
        self._enforce_cap(function)
        return path

    def _enforce_cap(self, function: str) -> None:
        files = sorted(self.base.glob(f"{function}-*.json"))
        excess = len(files) - self.max_per_function
        for f in files[:max(0, excess)]:
            try:
                f.unlink()
            except OSError:
                pass

    def latest(self, function: str) -> Path | None:
        files = sorted(self.base.glob(f"{function}-*.json"))
        return files[-1] if files else None
