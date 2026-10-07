from __future__ import annotations

import json


def float_value(value: object, *, default: float = 0.0) -> float:
    if not value:
        return float(default)
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float, str)):
        return float(value)
    raise TypeError(f"expected a numeric value, got {type(value).__name__}")


def int_value(value: object, *, default: int = 0) -> int:
    if not value:
        return int(default)
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float, str)):
        return int(value)
    raise TypeError(f"expected an integer value, got {type(value).__name__}")


def string_object_dict(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    result: dict[str, object] = {}
    for key, item in value.items():
        if not isinstance(key, str):
            return None
        result[key] = item
    return result


def json_object(value: object, *, label: str = "JSON value") -> dict[str, object]:
    raw: str | bytes | bytearray
    if not value:
        raw = "{}"
    elif isinstance(value, (str, bytes, bytearray)):
        raw = value
    else:
        raise TypeError(f"{label} must be JSON text")

    decoded: object = json.loads(raw)
    result = string_object_dict(decoded)
    if result is None:
        raise TypeError(f"{label} must contain an object")
    return result
