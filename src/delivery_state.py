from __future__ import annotations

from collections.abc import Mapping
from enum import StrEnum
from typing import Any

RETRY_DELIVERY_STATUSES = frozenset({"retrying", "rate_limited"})
TERMINAL_DELIVERY_STATUSES = frozenset(
    {"cancelled", "dead_lettered", "outcome_unknown", "succeeded"}
)


class CompletionAction(StrEnum):
    COMPLETE = "complete"
    ACKNOWLEDGE = "acknowledge"
    REJECT = "reject"


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
