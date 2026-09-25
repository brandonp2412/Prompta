from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

from .jobs import PromptJob, _next_daily_epoch

INITIAL_DELAY_CAP_SECONDS = 30 * 60.0
RECURRING_JITTER_FRACTION = 0.20
RECURRING_JITTER_CAP_SECONDS = 5 * 60.0

_TERMINAL_DELIVERY_STATES = frozenset(
    {"succeeded", "dead_lettered", "cancelled", "outcome_unknown"}
)
_PENDING_DELIVERY_STATES = frozenset({"queued", "running", "retrying", "rate_limited"})
_SCHEDULE_MARKER_KEYS = (
    "last_sent_at",
    "last_uncertain_send_at",
    "last_enqueued_at",
    "initial_due_at_epoch",
    "next_due_at_epoch",
)


def prompt_hash(prompt: str) -> str:
    return hashlib.sha256(prompt.encode()).hexdigest()


def scheduled_job_prompt(job: PromptJob) -> str:
    if not job.source_revision:
        return job.prompt
    return (
        f"{job.prompt}\n\n"
        "Prompta job context: the Prompta source revision when this job was created was "
        f"{job.source_revision}. Use this revision when checking whether a reported bug predates "
        "later code changes."
    )


def _state_float(state: Mapping[str, Any], key: str) -> float:
    try:
        return float(state.get(key) or 0.0)
    except (TypeError, ValueError):
        return 0.0


def initial_jitter_window(job: PromptJob) -> float:
    return min(max(0.0, float(job.interval_seconds)), INITIAL_DELAY_CAP_SECONDS)


def initial_due_at(
    job: PromptJob,
    state: Mapping[str, Any],
    *,
    now: float,
    jitter_seconds: float = 0.0,
) -> float | None:
    if any(state.get(key) for key in _SCHEDULE_MARKER_KEYS):
        return None
    if job.run_at_epoch is not None:
        return float(job.run_at_epoch)
    if job.daily_at is not None:
        return _next_daily_epoch(job.daily_at, now, include_now=True)
    return now + max(0.0, float(jitter_seconds))


def recurring_jitter_cap(job: PromptJob) -> float:
    if job.exact_interval:
        return 0.0
    interval = max(0.0, float(job.interval_seconds))
    return min(RECURRING_JITTER_CAP_SECONDS, interval * RECURRING_JITTER_FRACTION)


def recurring_delay(job: PromptJob, *, jitter_seconds: float = 0.0) -> float:
    interval = max(0.0, float(job.interval_seconds))
    if job.exact_interval:
        return interval
    return interval + max(0.0, float(jitter_seconds))


def next_due_at(
    *,
    completed_at: float,
    one_time: bool,
    daily_at: str | None,
    interval_seconds: float,
    exact_interval: bool,
    jitter_seconds: float = 0.0,
) -> float:
    if one_time:
        return 0.0
    if daily_at is not None:
        return _next_daily_epoch(daily_at, completed_at)
    return completed_at + recurring_delay(
        PromptJob(
            "",
            "",
            interval_seconds,
            exact_interval=exact_interval,
        ),
        jitter_seconds=jitter_seconds,
    )


def due_in(job: PromptJob, state: Mapping[str, Any], *, now: float) -> float:
    try:
        last_sent_at = float(state.get("last_sent_at") or 0.0)
        last_uncertain_send_at = float(state.get("last_uncertain_send_at") or 0.0)
        next_due = float(state.get("next_due_at_epoch") or 0.0)
        initial_due = float(state.get("initial_due_at_epoch") or 0.0)
    except (TypeError, ValueError):
        return 0.0
    last_attempt_at = max(last_sent_at, last_uncertain_send_at)

    if job.run_at_epoch is not None:
        if last_attempt_at > 0:
            return float("inf")
        due_at = initial_due if initial_due > 0 else float(job.run_at_epoch)
        return max(0.0, due_at - now)
    if next_due > 0 and last_sent_at >= last_uncertain_send_at:
        return max(0.0, next_due - now)
    if last_attempt_at > 0:
        if job.daily_at is not None:
            return max(0.0, _next_daily_epoch(job.daily_at, last_attempt_at) - now)
        return max(0.0, last_attempt_at + max(0.0, float(job.interval_seconds)) - now)
    if initial_due > 0:
        return max(0.0, initial_due - now)
    return 0.0


def occurrence_marker(job: PromptJob, state: Mapping[str, Any]) -> float:
    try:
        last_sent_at = float(state.get("last_sent_at") or 0.0)
        last_uncertain_send_at = float(state.get("last_uncertain_send_at") or 0.0)
    except (TypeError, ValueError):
        last_sent_at = 0.0
        last_uncertain_send_at = 0.0
    keys = (
        ("last_uncertain_send_at",)
        if last_uncertain_send_at > last_sent_at
        else ("next_due_at_epoch", "initial_due_at_epoch", "last_sent_at")
    )
    marker = 0.0
    for key in keys:
        value = _state_float(state, key)
        if value > 0:
            marker = value
            break
    if job.run_at_epoch is not None:
        return float(job.run_at_epoch)
    return marker


def occurrence_key(job: PromptJob, state: Mapping[str, Any]) -> str:
    marker = occurrence_marker(job, state)
    raw = f"{job.name}\0{prompt_hash(job.prompt)}\0{marker:.6f}"
    return hashlib.sha256(raw.encode()).hexdigest()


def receipt_is_pending(receipt: Mapping[str, Any] | None) -> bool:
    if receipt is None:
        return False
    return str(receipt.get("status") or "") in _PENDING_DELIVERY_STATES


def receipt_is_terminal(receipt: Mapping[str, Any] | None) -> bool:
    if receipt is None:
        return False
    return str(receipt.get("status") or "") in _TERMINAL_DELIVERY_STATES


def should_enqueue_job(
    job: PromptJob,
    state: Mapping[str, Any],
    *,
    now: float,
    pending_delivery: bool,
) -> bool:
    return (
        state.get("paused") is not True
        and due_in(job, state, now=now) <= 0
        and not pending_delivery
    )


def send_gap_remaining(*, last_attempt_at: Any, gap_seconds: float, now: float) -> float:
    try:
        last_attempt = float(last_attempt_at or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, last_attempt + max(0.0, float(gap_seconds)) - now)


def failure_retry_remaining(
    *,
    persisted_retry_until: Any,
    in_memory_retry_until: float,
    now: float,
) -> float:
    try:
        persisted = float(persisted_retry_until or 0.0)
    except (TypeError, ValueError):
        persisted = 0.0
    return max(0.0, max(persisted, float(in_memory_retry_until)) - now)


def retry_at(*, now: float, delay_seconds: float) -> float:
    return float(now) + max(0.0, float(delay_seconds))


def failure_state_updates(
    message: str,
    *,
    status_at: float,
    retry_until: float | None = None,
) -> dict[str, Any]:
    updates: dict[str, Any] = {
        "status": "failing",
        "status_message": message,
        "status_at": float(status_at),
    }
    if retry_until is not None:
        updates["failure_retry_until_epoch"] = float(retry_until)
    return updates


def pending_delivery_updates(
    job: PromptJob,
    *,
    send_id: str,
    idempotency_key: str,
    queued_at: float,
) -> dict[str, Any]:
    return {
        "last_enqueued_at": float(queued_at),
        "last_delivery_send_id": send_id,
        "last_delivery_idempotency_key": idempotency_key,
        "pending_delivery_prompt_sha256": prompt_hash(job.prompt),
        "pending_delivery_interval_seconds": float(job.interval_seconds),
        "pending_delivery_daily_at": job.daily_at or "",
        "pending_delivery_exact_interval": bool(job.exact_interval),
        "pending_delivery_one_time": job.run_at_epoch is not None,
        "status": "queued",
        "status_message": "",
        "status_at": float(queued_at),
    }


def successful_delivery_updates(
    intent: Mapping[str, Any],
    *,
    conversation_id: str,
    sent_at: float,
    next_due_at_epoch: float,
    rate_limit_backoff: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "prompt_sha256": str(intent.get("job_prompt_sha256") or ""),
        "last_sent_at": float(sent_at),
        "last_uncertain_send_at": 0.0,
        "initial_due_at_epoch": 0.0,
        "next_due_at_epoch": float(next_due_at_epoch),
        "last_conversation_id": conversation_id,
        "rate_limit_backoff": dict(rate_limit_backoff),
        "failure_retry_until_epoch": 0.0,
        "status": "healthy",
        "status_message": "",
        "status_at": float(sent_at),
    }


def terminal_reconciliation_updates(
    state: Mapping[str, Any],
    receipt: Mapping[str, Any],
    *,
    fallback_completed_at: float,
    jitter_seconds: float = 0.0,
) -> dict[str, Any] | None:
    send_id = str(receipt.get("send_id") or "")
    if not send_id or str(state.get("last_completed_delivery_send_id") or "") == send_id:
        return None

    completed_at = float(
        receipt.get("finished_at")
        or receipt.get("updated_at")
        or receipt.get("created_at")
        or fallback_completed_at
    )
    one_time = bool(state.get("pending_delivery_one_time"))
    daily_at = str(state.get("pending_delivery_daily_at") or "") or None
    interval_seconds = _state_float(state, "pending_delivery_interval_seconds")
    exact_interval = bool(state.get("pending_delivery_exact_interval"))
    status = str(receipt.get("status") or "")

    updates: dict[str, Any] = {
        "initial_due_at_epoch": 0.0,
        "next_due_at_epoch": next_due_at(
            completed_at=completed_at,
            one_time=one_time,
            daily_at=daily_at,
            interval_seconds=interval_seconds,
            exact_interval=exact_interval,
            jitter_seconds=jitter_seconds,
        ),
        "last_completed_delivery_send_id": send_id,
        "status_at": completed_at,
    }
    if status == "succeeded":
        updates.update(
            {
                "prompt_sha256": str(state.get("pending_delivery_prompt_sha256") or ""),
                "last_sent_at": completed_at,
                "last_uncertain_send_at": 0.0,
                "last_conversation_id": str(receipt.get("conversation_id") or ""),
                "failure_retry_until_epoch": 0.0,
                "status": "healthy",
                "status_message": "",
            }
        )
    else:
        updates.update(
            {
                "status": "failing",
                "status_message": str(receipt.get("last_error") or receipt.get("error") or status),
            }
        )
    return updates
