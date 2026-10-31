"""Bounded tool-call snapshots shared by results and manual replies."""

import json


def serialize_tool_calls(calls: tuple[dict[str, object], ...]) -> str:
    """Persist bounded display data only; never source SSE frames or thoughts."""
    selected: list[dict[str, object]] = []
    for call in calls[:128]:
        candidate = json.dumps([*selected, call], ensure_ascii=False)
        if len(candidate) > 512_000:
            break
        selected.append(call)
    return json.dumps(selected, ensure_ascii=False)


def deserialize_tool_calls(value: object) -> list[dict[str, object]]:
    if not isinstance(value, str):
        return []
    try:
        parsed: object = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [
        {key: child for key, child in item.items() if isinstance(key, str)}
        for item in parsed[:128]
        if isinstance(item, dict)
    ]


def merge_tool_calls(previous: object, incoming: tuple[dict[str, object], ...]) -> str:
    """Merge successive owned SSE snapshots by invocation ID without dropping earlier calls."""
    if not incoming:
        return previous if isinstance(previous, str) else "[]"
    merged = deserialize_tool_calls(previous)
    # Replace only corresponding DOM headings. One structured invocation must
    # not erase other visible calls (e.g. a subsequent connector POST).

    def same_activity(dom: dict[str, object], stream: dict[str, object]) -> bool:
        label = str(dom.get("action", "")).casefold().removeprefix("used ").strip()
        names = (str(stream.get(field, "")).casefold().strip() for field in ("connector", "action"))
        return label == "tool activity" or label in names

    stream_calls = [
        call for call in (*merged, *incoming) if not str(call.get("id", "")).startswith("dom-tool-")
    ]
    upgraded: list[dict[str, object]] = []
    upgraded_ids: set[str] = set()
    for call in merged:
        if str(call.get("id", "")).startswith("dom-tool-"):
            call = next((stream for stream in stream_calls if same_activity(call, stream)), call)
        identifier = str(call.get("id"))
        if identifier not in upgraded_ids:
            upgraded.append(call)
            upgraded_ids.add(identifier)
    merged = upgraded
    incoming = tuple(
        call
        for call in incoming
        if not (
            str(call.get("id", "")).startswith("dom-tool-")
            and any(same_activity(call, stream) for stream in stream_calls)
        )
    )
    by_id = {str(call.get("id")): i for i, call in enumerate(merged)}
    for call in incoming:
        identifier = str(call.get("id"))
        if identifier in by_id:
            index = by_id[identifier]
            old = merged[index]
            refreshed = {**old, **call}
            for field in ("arguments", "result", "error"):
                if not call.get(field) and field in old:
                    refreshed[field] = old[field]
            if old.get("status") in ("completed", "error") and call.get("status") == "running":
                refreshed["status"] = old["status"]
            merged[index] = refreshed
        elif len(merged) < 128:
            by_id[identifier] = len(merged)
            merged.append(call)
    return serialize_tool_calls(tuple(merged))
