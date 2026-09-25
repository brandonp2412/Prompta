"""Pure completion/reconciliation decisions for tracked conversations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from .structured_capture import has_completed_final_text, message_parts_from_source_events


def _structured_tool_turn_missing_final_text(snapshot: dict[str, Any]) -> bool:
    events = snapshot.get("source_events")
    if not isinstance(events, list) or not events:
        return False
    parts = message_parts_from_source_events(events)
    has_tool_call = any(
        isinstance(part, dict) and str(part.get("kind") or "") == "tool_call" for part in parts
    )
    return has_tool_call and not has_completed_final_text(parts)


@dataclass(frozen=True)
class CompletionAssessment:
    message_count: int
    waiting_for_latest_assistant: bool
    snapshot_has_latest_user: bool
    has_assistant: bool
    streaming: bool
    missing_latest_assistant: bool
    fallback_completion: bool
    missing_final_text: bool
    completion_polls: int


def assess_snapshot_completion(
    snapshot: dict[str, Any],
    durable_messages: list[dict[str, Any]],
    activity: dict[str, Any],
    *,
    completion_hint: bool,
    failure_hint: bool,
    completion_polls: int,
    fallback_completion_polls: int,
) -> CompletionAssessment:
    raw_messages = snapshot.get("messages")
    messages = raw_messages if isinstance(raw_messages, list) else []
    latest_durable = durable_messages[-1] if durable_messages else None
    waiting_for_latest_assistant = (
        isinstance(latest_durable, dict)
        and str(latest_durable.get("role") or "") == "user"
        and bool(str(latest_durable.get("content") or "").strip())
    )

    snapshot_has_latest_user = True
    if waiting_for_latest_assistant:
        latest_user_key = str(latest_durable.get("message_key") or "")
        latest_user_text = str(latest_durable.get("content") or "").strip()
        snapshot_has_latest_user = any(
            isinstance(message, dict)
            and str(message.get("role") or "") == "user"
            and (
                (latest_user_key and str(message.get("id") or "") == latest_user_key)
                or str(message.get("content") or "").strip() == latest_user_text
            )
            for message in messages
        )

    last_message = messages[-1] if messages else None
    has_assistant = (
        snapshot_has_latest_user
        and isinstance(last_message, dict)
        and str(last_message.get("role") or "") == "assistant"
        and bool(str(last_message.get("content") or "").strip())
    )
    streaming = bool(snapshot.get("streaming"))
    missing_latest_assistant = (
        waiting_for_latest_assistant
        and snapshot_has_latest_user
        and activity.get("complete") is True
        and not streaming
        and not failure_hint
        and not has_assistant
    )
    fallback_completion = (
        completion_hint and "turn_ended" in activity and activity.get("turn_ended") is None
    )
    missing_final_text = missing_latest_assistant or (
        fallback_completion and _structured_tool_turn_missing_final_text(snapshot)
    )

    return CompletionAssessment(
        message_count=len(messages),
        waiting_for_latest_assistant=waiting_for_latest_assistant,
        snapshot_has_latest_user=snapshot_has_latest_user,
        has_assistant=has_assistant,
        streaming=streaming,
        missing_latest_assistant=missing_latest_assistant,
        fallback_completion=fallback_completion,
        missing_final_text=missing_final_text,
        completion_polls=(fallback_completion_polls if fallback_completion else completion_polls),
    )


def advance_completion_poll(
    *,
    idle_polls: int,
    settled_at: float,
    changed: bool,
    completion_hint: bool,
    streaming: bool,
    has_assistant: bool,
    missing_latest_assistant: bool,
) -> tuple[int, float]:
    if settled_at > 0 and completion_hint and not streaming:
        return idle_polls, settled_at
    if not changed and not streaming and (has_assistant or missing_latest_assistant):
        return idle_polls + 1, settled_at
    return 0, 0.0


class RecoveryAction(StrEnum):
    WAIT = "wait"
    RETRY = "retry"
    RELOAD = "reload"
    INTERRUPT = "interrupt"


@dataclass(frozen=True)
class TransientRecoveryDecision:
    action: RecoveryAction
    transient_since_epoch: float


def transient_recovery_decision(
    *,
    now_epoch: float,
    transient_since_epoch: float,
    recovered_cache_updated_at: float,
    recovery_attempts: int,
    recovery_delay_seconds: float,
    failure_timeout_seconds: float,
) -> TransientRecoveryDecision:
    started_at = transient_since_epoch
    if started_at <= 0:
        started_at = (
            min(now_epoch, recovered_cache_updated_at)
            if recovered_cache_updated_at > 0
            else now_epoch
        )
    timeout = recovery_delay_seconds if recovery_attempts <= 0 else failure_timeout_seconds
    action = RecoveryAction.WAIT
    if now_epoch - started_at >= timeout:
        action = RecoveryAction.RELOAD if recovery_attempts <= 0 else RecoveryAction.INTERRUPT
    return TransientRecoveryDecision(action=action, transient_since_epoch=started_at)


def delivery_failure_action(
    *,
    now_monotonic: float,
    idle_polls: int,
    retry_attempts: int,
    retry_at: float,
    recovery_attempts: int,
    recovery_at: float,
    failure_polls: int,
    retry_discovery_polls: int,
    retry_max_attempts: int,
    retry_grace_seconds: float,
    recovery_max_attempts: int,
    recovery_grace_seconds: float,
    retry_control_failed: bool = False,
) -> RecoveryAction:
    if recovery_at > 0 and now_monotonic - recovery_at < recovery_grace_seconds:
        return RecoveryAction.WAIT
    if retry_at > 0 and now_monotonic - retry_at < retry_grace_seconds:
        return RecoveryAction.WAIT
    if idle_polls < failure_polls:
        return RecoveryAction.WAIT
    if retry_attempts < retry_max_attempts:
        if not retry_control_failed:
            return RecoveryAction.RETRY
        if idle_polls < failure_polls + retry_discovery_polls:
            return RecoveryAction.WAIT
    if recovery_attempts < recovery_max_attempts:
        return RecoveryAction.RELOAD
    return RecoveryAction.INTERRUPT


@dataclass(frozen=True)
class FinalTextRecoveryDecision:
    action: RecoveryAction
    missing_since_epoch: float
    timeout_expired: bool


def final_text_recovery_decision(
    *,
    now_epoch: float,
    missing_since_epoch: float,
    recovery_attempts: int,
    max_recovery_attempts: int,
    failure_timeout_seconds: float,
) -> FinalTextRecoveryDecision:
    started_at = missing_since_epoch if missing_since_epoch > 0 else now_epoch
    timeout_expired = now_epoch - started_at >= failure_timeout_seconds
    if recovery_attempts < max_recovery_attempts:
        action = RecoveryAction.RELOAD
    elif timeout_expired:
        action = RecoveryAction.INTERRUPT
    else:
        action = RecoveryAction.WAIT
    return FinalTextRecoveryDecision(
        action=action,
        missing_since_epoch=started_at,
        timeout_expired=timeout_expired,
    )
