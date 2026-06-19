"""Reactive diagnostics: detect broken driver calls + capture evidence.

When ChatGPT changes its API/UI, driver methods silently return wrong shapes.
This module classifies results against an expected-shape registry so breakage
is caught at the moment it happens, then (in later tasks) captures the evidence.
"""

from __future__ import annotations

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
