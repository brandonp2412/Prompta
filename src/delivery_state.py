from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, TypeVar

WAITING_DELIVERY_STATUSES = frozenset({"queued", "retrying", "rate_limited"})
RETRY_DELIVERY_STATUSES = frozenset({"retrying", "rate_limited"})
TERMINAL_DELIVERY_STATUSES = frozenset(
    {"cancelled", "dead_lettered", "outcome_unknown", "succeeded"}
)
ACTIVE_DELIVERY_STATUSES = WAITING_DELIVERY_STATUSES | {"running"}
CANCELLABLE_DELIVERY_STATUSES = ACTIVE_DELIVERY_STATUSES | {
    "failed",
    "dead_lettered",
    "outcome_unknown",
}
ATTACHMENT_RETAINING_STATUSES = {
    "queued",
    "running",
    "retrying",
    "rate_limited",
    "dead_lettered",
    "outcome_unknown",
}


class CompletionAction(StrEnum):
    COMPLETE = "complete"
    ACKNOWLEDGE = "acknowledge"
    REJECT = "reject"


class FailureKind(StrEnum):
    OUTCOME_UNKNOWN = "outcome_unknown"
    DEFERRED = "deferred"
    INFRASTRUCTURE = "infrastructure"
    GENERIC = "generic"
    RATE_LIMITED = "rate_limited"


@dataclass(frozen=True)
class DeliveryTransition:
    status: str
    error: str
    retry_at: float = 0.0
    retry_after_seconds: int = 0
    retry_attempt: int = 0
    infrastructure_retry_attempt: int = 0
    finished_at: float = 0.0

    @property
    def retries(self) -> bool:
        return self.status in RETRY_DELIVERY_STATUSES

    @property
    def terminal(self) -> bool:
        return self.status in TERMINAL_DELIVERY_STATUSES


@dataclass(frozen=True)
class CoalescedReply:
    send_id: str
    primary_client_id: str
    message: str
    attachments: tuple[str, ...]
    created_at: float


_Job = TypeVar("_Job")


def existing_client_job(
    client_id: str,
    client_jobs: Mapping[str, str],
    jobs: Mapping[str, _Job],
) -> _Job | None:
    if not client_id:
        return None
    send_id = client_jobs.get(client_id)
    if not send_id:
        return None
    return jobs.get(send_id)


def coalesce_queued_reply(
    jobs: Iterable[Mapping[str, Any]],
    *,
    conversation_id: str,
    message: str,
    attachments: Iterable[str],
) -> CoalescedReply | None:
    if not conversation_id:
        return None

    incoming_attachments = tuple(str(value) for value in attachments)
    for existing in jobs:
        if (
            str(existing.get("operation") or "") != "reply"
            or str(existing.get("conversation_id") or "") != conversation_id
            or str(existing.get("status") or "") != "queued"
        ):
            continue

        raw_existing_attachments = existing.get("_attachments", [])
        existing_attachments = (
            tuple(str(value) for value in raw_existing_attachments if isinstance(value, str))
            if isinstance(raw_existing_attachments, list)
            else ()
        )
        existing_message = str(existing.get("message") or "")
        merged_message = "\n".join(value for value in (existing_message, message) if value)
        return CoalescedReply(
            send_id=str(existing.get("send_id") or ""),
            primary_client_id=str(existing.get("client_id") or ""),
            message=merged_message,
            attachments=existing_attachments + incoming_attachments,
            created_at=float(existing.get("created_at") or 0.0),
        )
    return None


def claimable_delivery(record: Mapping[str, Any], *, now: float) -> bool:
    status = str(record.get("status") or "")
    if status == "queued":
        return True
    if status in RETRY_DELIVERY_STATUSES:
        return float(record.get("retry_at") or 0.0) <= now
    if status == "running":
        return float(record.get("lease_expires_at") or 0.0) <= now
    return False


def renewable_delivery_lease(
    record: Mapping[str, Any],
    *,
    owner: str,
    now: float,
) -> bool:
    return (
        str(record.get("status") or "") == "running"
        and str(record.get("lease_owner") or "") == owner
        and float(record.get("lease_expires_at") or 0.0) > now
    )


def owned_running_delivery(record: Mapping[str, Any], *, owner: str) -> bool:
    return (
        str(record.get("status") or "") == "running"
        and str(record.get("lease_owner") or "") == owner
    )


def completion_action(record: Mapping[str, Any], *, owner: str) -> CompletionAction:
    status = str(record.get("status") or "")
    if status == "succeeded":
        return CompletionAction.ACKNOWLEDGE
    if status != "running" or status in TERMINAL_DELIVERY_STATUSES:
        return CompletionAction.REJECT
    if str(record.get("lease_owner") or "") != owner:
        return CompletionAction.REJECT
    return CompletionAction.COMPLETE


def exponential_retry_delay(
    attempt: int,
    *,
    base_seconds: float,
    cap_seconds: float,
) -> float:
    exponent = max(0, int(attempt) - 1)
    return min(float(cap_seconds), float(base_seconds) * (2**exponent))


def decide_failure_transition(
    *,
    kind: FailureKind,
    now: float,
    error: str,
    generic_attempt: int,
    infrastructure_attempt: int,
    max_generic_attempts: int,
    retry_base_seconds: float,
    retry_cap_seconds: float,
    delay_seconds: float = 0.0,
    rate_limit_attempt: int = 0,
) -> DeliveryTransition:
    generic_attempt = max(0, int(generic_attempt))
    infrastructure_attempt = max(0, int(infrastructure_attempt))

    if kind is FailureKind.OUTCOME_UNKNOWN:
        return DeliveryTransition(
            status="outcome_unknown",
            error=error,
            retry_attempt=generic_attempt,
            infrastructure_retry_attempt=infrastructure_attempt,
            finished_at=now,
        )

    if kind is FailureKind.DEFERRED:
        delay = max(0.0, float(delay_seconds))
        return DeliveryTransition(
            status="retrying",
            error=error,
            retry_at=now + delay,
            retry_after_seconds=max(1, math.ceil(delay)),
            retry_attempt=generic_attempt,
            infrastructure_retry_attempt=infrastructure_attempt,
        )

    if kind is FailureKind.INFRASTRUCTURE:
        next_infrastructure_attempt = infrastructure_attempt + 1
        delay = exponential_retry_delay(
            next_infrastructure_attempt,
            base_seconds=retry_base_seconds,
            cap_seconds=retry_cap_seconds,
        )
        return DeliveryTransition(
            status="retrying",
            error=error,
            retry_at=now + delay,
            retry_after_seconds=max(1, math.ceil(delay)),
            retry_attempt=generic_attempt,
            infrastructure_retry_attempt=next_infrastructure_attempt,
        )

    if kind is FailureKind.RATE_LIMITED:
        delay = max(0.0, float(delay_seconds))
        attempt = max(1, int(rate_limit_attempt))
        return DeliveryTransition(
            status="rate_limited",
            error=error,
            retry_at=now + delay,
            retry_after_seconds=max(1, math.ceil(delay)),
            retry_attempt=attempt,
            infrastructure_retry_attempt=infrastructure_attempt,
        )

    next_generic_attempt = generic_attempt + 1
    if next_generic_attempt >= max(1, int(max_generic_attempts)):
        return DeliveryTransition(
            status="dead_lettered",
            error=error,
            retry_attempt=next_generic_attempt,
            infrastructure_retry_attempt=infrastructure_attempt,
        )

    delay = exponential_retry_delay(
        next_generic_attempt,
        base_seconds=retry_base_seconds,
        cap_seconds=retry_cap_seconds,
    )
    return DeliveryTransition(
        status="retrying",
        error=error,
        retry_at=now + delay,
        retry_after_seconds=max(1, math.ceil(delay)),
        retry_attempt=next_generic_attempt,
        infrastructure_retry_attempt=infrastructure_attempt,
    )


def normalize_recovery_status(
    raw_status: str,
    *,
    retry_at: float,
    retry_attempt: int,
) -> str:
    status = raw_status.strip()
    if not status:
        return "rate_limited" if retry_at > 0 or retry_attempt > 0 else "queued"
    if status in TERMINAL_DELIVERY_STATUSES | ACTIVE_DELIVERY_STATUSES:
        return status
    return "queued"


def expired_running_lease(
    status: str,
    *,
    lease_expires_at: float,
    now: float,
) -> bool:
    return status == "running" and lease_expires_at <= now


def should_cleanup_attachments(status: str) -> bool:
    return status not in ATTACHMENT_RETAINING_STATUSES
