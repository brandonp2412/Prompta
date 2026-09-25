"""Pure transcript snapshot reconciliation decisions.

This module is deliberately free of database, browser, clock, and worker ownership.
The imperative cache shell supplies observed state and persists the returned decisions.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .chromium import finalize_completed_assistant_content, preserves_non_tool_text
from .structured_capture import (
    has_completed_final_text,
    message_parts_from_source_events,
    rendered_content_from_parts,
)
from .ui_noise import strip_assistant_ui_noise


@dataclass(frozen=True)
class IncomingMessage:
    snapshot_index: int
    role: str
    content: str
    message_key: str


@dataclass(frozen=True)
class SnapshotCoverage:
    is_full: bool
    superseded_stable_keys: frozenset[str]


def normalize_snapshot_messages(
    snapshot: dict[str, Any],
    *,
    complete: bool,
) -> tuple[list[Any], list[dict[str, Any]]]:
    raw_messages = snapshot.get("messages")
    messages = (
        [dict(message) if isinstance(message, dict) else message for message in raw_messages]
        if isinstance(raw_messages, list)
        else []
    )
    raw_source_events = snapshot.get("source_events")
    structured_events = (
        [event for event in raw_source_events if isinstance(event, dict)]
        if isinstance(raw_source_events, list)
        else []
    )

    has_dom_prose_fallback = any(
        str(event.get("id") or "").endswith(":dom-prose") for event in structured_events
    )
    if structured_events:
        ordered_parts = message_parts_from_source_events(structured_events)
        ordered_content = rendered_content_from_parts(ordered_parts)
        trusted_completed_content = (
            complete and has_dom_prose_fallback and has_completed_final_text(ordered_parts)
        )
        if ordered_content and (not has_dom_prose_fallback or trusted_completed_content):
            for message in reversed(messages):
                if not isinstance(message, dict) or str(message.get("role") or "") != "assistant":
                    continue
                visible_content = str(message.get("content") or "")
                if trusted_completed_content or preserves_non_tool_text(
                    visible_content,
                    ordered_content,
                ):
                    message["content"] = ordered_content
                break

    if complete:
        for message in reversed(messages):
            if not isinstance(message, dict) or str(message.get("role") or "") != "assistant":
                continue
            message["content"] = finalize_completed_assistant_content(
                str(message.get("content") or "")
            )
            break

    return messages, structured_events


def incoming_messages(messages: list[Any]) -> tuple[IncomingMessage, ...]:
    incoming: list[IncomingMessage] = []
    for snapshot_index, message in enumerate(messages):
        if not isinstance(message, dict):
            continue
        role = str(message.get("role") or "")
        content = str(message.get("content") or "")
        if role == "assistant":
            content = strip_assistant_ui_noise(content)
        raw_key = str(message.get("id") or "")
        message_key = raw_key or f"{role}:{snapshot_index}"
        if role == "assistant" and message_key.startswith("request-placeholder-"):
            continue
        incoming.append(
            IncomingMessage(
                snapshot_index=snapshot_index,
                role=role,
                content=content,
                message_key=message_key,
            )
        )
    return tuple(incoming)


def classify_snapshot_coverage(
    incoming: tuple[IncomingMessage, ...],
    existing_history: list[dict[str, Any]],
) -> SnapshotCoverage:
    first_incoming = incoming[0] if incoming else None
    first_existing = existing_history[0] if existing_history else None
    snapshot_is_full = first_existing is None
    if first_incoming is not None and first_existing is not None:
        snapshot_is_full = first_incoming.message_key == str(first_existing["message_key"]) or (
            first_incoming.role == str(first_existing["role"])
            and first_incoming.content.strip() == str(first_existing["content"]).strip()
        )

    if not snapshot_is_full or not existing_history:
        return SnapshotCoverage(is_full=snapshot_is_full, superseded_stable_keys=frozenset())

    # ChatGPT virtualizes older turns. A DOM snapshot can begin at the first
    # cached message while still omitting a stable message in the middle.
    # Treat that as partial; otherwise snapshot indexes can reuse occupied
    # ordinals and make legitimate messages render as duplicates. The one
    # safe exception is a stale assistant sibling within a user turn that
    # still has another canonical assistant represented in the snapshot.
    unmatched_incoming = list(incoming)
    stable_existing = [
        row
        for row in existing_history
        if str(row["status"]) == "complete"
        and not str(row["message_key"]).startswith("__prompta_live_assistant_")
        and not str(row["message_key"]).startswith("request-placeholder-")
    ]
    matched_stable_keys: set[str] = set()
    missing_stable: list[dict[str, Any]] = []
    for existing in stable_existing:
        existing_key = str(existing["message_key"])
        existing_role = str(existing["role"])
        existing_content = str(existing["content"] or "").strip()
        match_index = next(
            (
                index
                for index, message in enumerate(unmatched_incoming)
                if message.message_key == existing_key
            ),
            -1,
        )
        if match_index < 0:
            match_index = next(
                (
                    index
                    for index, message in enumerate(unmatched_incoming)
                    if message.role == existing_role and message.content.strip() == existing_content
                ),
                -1,
            )
        if match_index < 0:
            missing_stable.append(existing)
            continue
        matched_stable_keys.add(existing_key)
        unmatched_incoming.pop(match_index)

    stable_users = [row for row in stable_existing if str(row["role"]) == "user"]
    superseded_stable_keys: set[str] = set()
    for missing in missing_stable:
        if str(missing["role"]) != "assistant":
            return SnapshotCoverage(is_full=False, superseded_stable_keys=frozenset())
        missing_ordinal = int(missing["ordinal"])
        previous_user_ordinal = max(
            (int(row["ordinal"]) for row in stable_users if int(row["ordinal"]) < missing_ordinal),
            default=-1,
        )
        next_user_ordinal = min(
            (int(row["ordinal"]) for row in stable_users if int(row["ordinal"]) > missing_ordinal),
            default=2_147_483_647,
        )
        matched_assistant_sibling = any(
            str(row["role"]) == "assistant"
            and str(row["message_key"]) in matched_stable_keys
            and previous_user_ordinal < int(row["ordinal"]) < next_user_ordinal
            for row in stable_existing
        )
        if not matched_assistant_sibling:
            return SnapshotCoverage(is_full=False, superseded_stable_keys=frozenset())
        superseded_stable_keys.add(str(missing["message_key"]))

    return SnapshotCoverage(
        is_full=True,
        superseded_stable_keys=frozenset(superseded_stable_keys),
    )


def resolve_streaming_message_key(
    message: IncomingMessage,
    *,
    preceding_user_key: str,
    current_by_key: dict[str, dict[str, Any]],
) -> str:
    message_key = message.message_key
    if (
        message.role != "assistant"
        or not message_key.startswith("__prompta_live_assistant_")
        or message_key in current_by_key
        or preceding_user_key not in current_by_key
    ):
        return message_key

    target_ordinal = int(current_by_key[preceding_user_key]["ordinal"]) + 1
    incoming_content = message.content.strip()
    for candidate_key, candidate in current_by_key.items():
        if candidate_key.startswith("__prompta_live_assistant_"):
            continue
        if str(candidate["role"]) != "assistant":
            continue
        if int(candidate["ordinal"]) != target_ordinal:
            continue
        candidate_content = str(candidate["content"] or "").strip()
        if (
            candidate_content
            and incoming_content
            and (
                candidate_content == incoming_content
                or candidate_content.startswith(incoming_content)
                or incoming_content.startswith(candidate_content)
            )
        ):
            return candidate_key
    return message_key


def select_handoff_candidate(
    *,
    role: str,
    message_key: str,
    existing: dict[str, Any] | None,
    preceding_user_key: str,
    current_by_key: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if (
        role != "assistant"
        or message_key.startswith("__prompta_live_assistant_")
        or existing is not None
        or preceding_user_key not in current_by_key
    ):
        return None

    expected_ordinal = int(current_by_key[preceding_user_key]["ordinal"]) + 1
    candidates = [
        candidate
        for candidate_key, candidate in current_by_key.items()
        if candidate_key != message_key
        and str(candidate.get("role") or "") == "assistant"
        and int(candidate.get("ordinal") or -1) == expected_ordinal
    ]
    if not candidates:
        return None
    return max(
        candidates,
        key=lambda candidate: (
            str(candidate.get("message_key") or "").startswith("__prompta_live_assistant_"),
            str(candidate.get("status") or "") == "streaming",
            float(candidate.get("updated_at") or 0.0),
        ),
    )


def snapshot_message_status(
    message: IncomingMessage,
    *,
    message_count: int,
    complete: bool,
    streaming: bool,
) -> str:
    if (
        not complete
        and streaming
        and message.snapshot_index == message_count - 1
        and message.role == "assistant"
    ):
        return "streaming"
    return "complete"
