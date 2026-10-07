from __future__ import annotations

import time
from collections.abc import Mapping
from pathlib import Path

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import Connection

from .delivery_state import (
    RETRY_DELIVERY_STATUSES,
    TERMINAL_DELIVERY_STATUSES,
    CompletionAction,
    completion_action,
)
from .persistence import create_database, job_deliveries
from .strict_types import float_value, int_value


class DeliveryQueueStore:
    """SQLAlchemy backed store for scheduled fresh-chat job deliveries."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self.engine = create_database(self.path, timeout=30.0)

    def connect(self) -> Connection:
        return self.engine.connect()

    @staticmethod
    def record_from_row(row: Mapping[str, object]) -> dict[str, object]:
        return {
            "send_id": str(row["send_id"]),
            "message": str(row["message"]),
            "client_id": str(row["client_id"] or ""),
            "status": str(row["status"] or "queued"),
            "error": str(row["error"] or ""),
            "last_error": str(row["last_error"] or ""),
            "created_at": float_value(row.get("created_at")),
            "updated_at": float_value(row.get("updated_at")),
            "retry_at": float_value(row.get("retry_at")),
            "retry_attempt": int_value(row.get("retry_attempt")),
            "finished_at": float_value(row.get("finished_at")),
            "lease_owner": str(row["lease_owner"] or ""),
            "lease_acquired_at": float_value(row.get("lease_acquired_at")),
            "lease_expires_at": float_value(row.get("lease_expires_at")),
        }

    def records(self) -> list[dict[str, object]]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(select(job_deliveries).order_by(job_deliveries.c.sequence))
                .mappings()
                .all()
            )
        return [self.record_from_row(row) for row in rows]

    def health_metrics(self, *, now: float | None = None) -> dict[str, object]:
        at = time.time() if now is None else float(now)
        pending = ("queued", "retrying", "rate_limited", "running")
        with self.engine.begin() as connection:
            counts = connection.execute(
                select(job_deliveries.c.status, func.count().label("count")).group_by(
                    job_deliveries.c.status
                )
            ).all()
            oldest_at = connection.execute(
                select(func.min(job_deliveries.c.created_at)).where(
                    job_deliveries.c.status.in_(pending)
                )
            ).scalar_one()
            last_success = connection.execute(
                select(job_deliveries.c.finished_at)
                .where(job_deliveries.c.status == "succeeded")
                .order_by(job_deliveries.c.finished_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        count_by_status = {str(status): int(count) for status, count in counts}
        oldest = float(oldest_at or 0.0)
        return {
            "queued": count_by_status.get("queued", 0),
            "running": count_by_status.get("running", 0),
            "retrying": count_by_status.get("retrying", 0),
            "rate_limited": count_by_status.get("rate_limited", 0),
            "dead_lettered": count_by_status.get("dead_lettered", 0),
            "outcome_unknown": count_by_status.get("outcome_unknown", 0),
            "oldest_pending_age_seconds": max(0.0, at - oldest) if oldest else 0.0,
            "last_successful_delivery_at": float(last_success or 0.0),
        }

    def get(self, send_id: str) -> dict[str, object] | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    select(job_deliveries).where(job_deliveries.c.send_id == send_id)
                )
                .mappings()
                .one_or_none()
            )
        return self.record_from_row(row) if row is not None else None

    def enqueue_idempotent(self, record: dict[str, object]) -> tuple[dict[str, object], bool]:
        send_id, message, client_id = (
            str(record.get(key) or "") for key in ("send_id", "message", "client_id")
        )
        if not send_id:
            raise ValueError("delivery send_id is required")
        if not message:
            raise ValueError("delivery message is required")
        now = float_value(record.get("created_at"), default=time.time())
        with self.engine.begin() as connection:
            values = {
                "send_id": send_id,
                "message": message,
                "client_id": client_id,
                "status": "queued",
                "error": "",
                "last_error": "",
                "created_at": now,
                "updated_at": now,
                "retry_at": 0,
                "retry_attempt": 0,
                "finished_at": 0,
            }
            result = connection.execute(
                insert(job_deliveries).values(**values).on_conflict_do_nothing()
            )
            row = (
                connection.execute(
                    select(job_deliveries).where(job_deliveries.c.send_id == send_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None and client_id:
                row = (
                    connection.execute(
                        select(job_deliveries).where(job_deliveries.c.client_id == client_id)
                    )
                    .mappings()
                    .one_or_none()
                )
            if row is None:
                raise RuntimeError("delivery insert completed without a matching queue record")
            return self.record_from_row(row), result.rowcount == 1

    def cancel_pending(
        self, send_id: str, *, error: str = "scheduled job cancelled", now: float | None = None
    ) -> bool:
        at = time.time() if now is None else float(now)
        with self.engine.begin() as connection:
            result = connection.execute(
                update(job_deliveries)
                .where(
                    job_deliveries.c.send_id == send_id,
                    job_deliveries.c.status.in_(("queued", "retrying", "rate_limited")),
                )
                .values(
                    status="cancelled",
                    error=error,
                    last_error=error,
                    retry_at=0,
                    finished_at=at,
                    updated_at=at,
                    lease_owner="",
                    lease_acquired_at=0,
                    lease_expires_at=0,
                )
            )
            return result.rowcount == 1

    def upsert(self, record: dict[str, object]) -> None:
        send_id, message = str(record.get("send_id") or ""), str(record.get("message") or "")
        if not send_id:
            raise ValueError("delivery send_id is required")
        if not message:
            raise ValueError("delivery message is required")
        created = float_value(record.get("created_at"), default=time.time())
        values: dict[str, object] = {
            "send_id": send_id,
            "message": message,
            "client_id": str(record.get("client_id") or ""),
            "status": str(record.get("status") or "queued"),
            "error": str(record.get("error") or ""),
            "last_error": str(record.get("last_error") or ""),
            "created_at": created,
            "updated_at": float_value(record.get("updated_at"), default=created),
            "retry_at": float_value(record.get("retry_at")),
            "retry_attempt": int_value(record.get("retry_attempt")),
            "finished_at": float_value(record.get("finished_at")),
            "lease_owner": str(record.get("lease_owner") or ""),
            "lease_acquired_at": float_value(record.get("lease_acquired_at")),
            "lease_expires_at": float_value(record.get("lease_expires_at")),
        }
        statement = insert(job_deliveries).values(**values)
        with self.engine.begin() as connection:
            connection.execute(
                statement.on_conflict_do_update(
                    index_elements=[job_deliveries.c.send_id],
                    set_={
                        key: getattr(statement.excluded, key) for key in values if key != "send_id"
                    },
                )
            )

    def claim_next(
        self, owner: str, *, lease_seconds: float, now: float | None = None
    ) -> dict[str, object] | None:
        at = time.time() if now is None else float(now)
        with self.engine.begin() as connection:
            claimable = or_(
                job_deliveries.c.status == "queued",
                job_deliveries.c.status.in_(RETRY_DELIVERY_STATUSES)
                & (job_deliveries.c.retry_at <= at),
                (job_deliveries.c.status == "running") & (job_deliveries.c.lease_expires_at <= at),
            )
            sequence = (
                select(job_deliveries.c.sequence)
                .where(claimable)
                .order_by(job_deliveries.c.sequence)
                .limit(1)
                .scalar_subquery()
            )
            row = (
                connection.execute(
                    update(job_deliveries)
                    .where(job_deliveries.c.sequence == sequence)
                    .values(
                        status="running",
                        updated_at=at,
                        lease_owner=owner,
                        lease_acquired_at=at,
                        lease_expires_at=at + max(1.0, float(lease_seconds)),
                    )
                    .returning(*job_deliveries.c)
                )
                .mappings()
                .one_or_none()
            )
        return self.record_from_row(row) if row is not None else None

    def renew_lease(
        self, send_id: str, owner: str, *, lease_seconds: float, now: float | None = None
    ) -> bool:
        at = time.time() if now is None else float(now)
        with self.engine.begin() as connection:
            result = connection.execute(
                update(job_deliveries)
                .where(
                    job_deliveries.c.send_id == send_id,
                    job_deliveries.c.status == "running",
                    job_deliveries.c.lease_owner == owner,
                    job_deliveries.c.lease_expires_at > at,
                )
                .values(updated_at=at, lease_expires_at=at + max(1.0, float(lease_seconds)))
            )
            return result.rowcount == 1

    def retry_claim(
        self,
        send_id: str,
        owner: str,
        *,
        retry_at: float,
        retry_attempt: int,
        error: str,
        status: str = "retrying",
        now: float | None = None,
    ) -> bool:
        if status not in RETRY_DELIVERY_STATUSES:
            raise ValueError(f"unsupported retry status: {status}")
        at = time.time() if now is None else float(now)
        with self.engine.begin() as connection:
            result = connection.execute(
                update(job_deliveries)
                .where(
                    job_deliveries.c.send_id == send_id,
                    job_deliveries.c.status == "running",
                    job_deliveries.c.lease_owner == owner,
                )
                .values(
                    status=status,
                    error=error,
                    last_error=error,
                    retry_at=float(retry_at),
                    retry_attempt=max(0, int(retry_attempt)),
                    updated_at=at,
                    lease_owner="",
                    lease_acquired_at=0,
                    lease_expires_at=0,
                )
            )
            return result.rowcount == 1

    def complete_claim(self, send_id: str, owner: str, *, now: float | None = None) -> bool:
        at = time.time() if now is None else float(now)
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    select(job_deliveries).where(job_deliveries.c.send_id == send_id)
                )
                .mappings()
                .one_or_none()
            )
            if row is None:
                return False
            action = completion_action(self.record_from_row(row), owner=owner)
            if action is CompletionAction.ACKNOWLEDGE:
                return True
            if action is CompletionAction.REJECT:
                return False
            result = connection.execute(
                update(job_deliveries)
                .where(
                    job_deliveries.c.send_id == send_id,
                    job_deliveries.c.status == "running",
                    job_deliveries.c.lease_owner == owner,
                )
                .values(
                    status="succeeded",
                    error="",
                    last_error="",
                    retry_at=0,
                    finished_at=case(
                        (job_deliveries.c.finished_at > 0, job_deliveries.c.finished_at), else_=at
                    ),
                    updated_at=at,
                    lease_owner="",
                    lease_acquired_at=0,
                    lease_expires_at=0,
                )
            )
            return result.rowcount == 1

    def fail_claim(
        self, send_id: str, owner: str, *, status: str, error: str, now: float | None = None
    ) -> bool:
        if status not in TERMINAL_DELIVERY_STATUSES or status == "succeeded":
            raise ValueError(f"unsupported terminal delivery status: {status}")
        at = time.time() if now is None else float(now)
        with self.engine.begin() as connection:
            result = connection.execute(
                update(job_deliveries)
                .where(
                    job_deliveries.c.send_id == send_id,
                    job_deliveries.c.status == "running",
                    job_deliveries.c.lease_owner == owner,
                )
                .values(
                    status=status,
                    error=error,
                    last_error=error,
                    retry_at=0,
                    finished_at=at,
                    updated_at=at,
                    lease_owner="",
                    lease_acquired_at=0,
                    lease_expires_at=0,
                )
            )
            return result.rowcount == 1
