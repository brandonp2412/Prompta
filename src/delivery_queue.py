from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import uuid
from collections.abc import Mapping
from functools import cached_property
from pathlib import Path

from sqlalchemy import case, func, or_, select, update
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import Connection
from sqlalchemy.exc import SQLAlchemyError

from .delivery_state import (
    RETRY_DELIVERY_STATUSES,
    TERMINAL_DELIVERY_STATUSES,
    CompletionAction,
    completion_action,
)
from .image_store import image_refs
from .persistence import create_database, job_deliveries
from .reply_contracts import ManualReplyStore
from .reply_tables import replies
from .response_store import ResponseStore
from .response_tables import results as response_records
from .strict_types import float_value, int_value

logger = logging.getLogger(__name__)
# Shared by actual claims and queue projections; never preempts active captures.
_DISPATCH_PRIORITY = case(
    (job_deliveries.c.client_id.like("manual:%"), 0),
    (job_deliveries.c.one_time.is_(True), 1),
    else_=2,
)
_EXPIRED_LEASE_ERROR = (
    "Worker lease expired before a durable send receipt; acceptance is unknown. "
    "Automatic resubmission is disabled."
)


class DeliveryQueueStore:
    """SQLAlchemy backed store for scheduled fresh-chat job deliveries."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self.engine = create_database(self.path, timeout=30.0)

    @cached_property
    def results(self) -> ResponseStore:
        return ResponseStore(self.path.parent / "chat-results.sqlite3")

    def _mark_result_unavailable(self, send_id: str) -> None:
        # The queue and transcript are separate SQLite databases. A failed
        # best-effort projection must not undo a terminal queue decision.
        try:
            self.results.unavailable(send_id)
        except (OSError, SQLAlchemyError) as exc:
            logger.warning(
                "Delivery result reconciliation deferred send_id=%s error_type=%s",
                send_id, type(exc).__name__,
            )

    @staticmethod
    def _expire_leases(connection: Connection, at: float) -> list[str]:
        # Once a send has been attempted, lease expiry cannot authorize replay.
        # This update is atomic with claim_next for multi-worker safety.
        expired_ids = connection.execute(
            update(job_deliveries)
            .where(
                job_deliveries.c.status == "running",
                job_deliveries.c.lease_expires_at <= at,
            )
            .values(
                status="outcome_unknown",
                error=_EXPIRED_LEASE_ERROR,
                last_error=_EXPIRED_LEASE_ERROR,
                updated_at=at,
                finished_at=at,
                retry_at=0,
                lease_owner="",
                lease_acquired_at=0,
                lease_expires_at=0,
            )
            .returning(job_deliveries.c.send_id)
        ).scalars().all()
        return [str(send_id) for send_id in expired_ids]

    def reconcile_accepted_outcomes(self, *, now: float | None = None) -> int:
        """Correct quarantined queue receipts only when local acceptance is proven.

        The capture and queue databases are separate. A browser may persist its
        verified acceptance before the queue worker loses its claim lease.
        A local accepted_at receipt is evidence to mark delivery successful;
        an absent receipt never authorizes a resend or a successful status.
        Only IDs and timestamps are queried, never private response text.
        """
        at = time.time() if now is None else float(now)
        with self.engine.connect() as connection:
            uncertain_ids = connection.execute(
                select(job_deliveries.c.send_id)
                .where(job_deliveries.c.status == "outcome_unknown")
            ).scalars().all()
        if not uncertain_ids:
            return 0
        try:
            with self.results.engine.begin() as connection:
                confirmed_ids = connection.execute(
                    select(response_records.c.send_id).where(
                        response_records.c.send_id.in_(uncertain_ids),
                        response_records.c.accepted_at > 0,
                        response_records.c.status.in_((
                            "accepted", "generating", "completed", "interrupted", "unavailable"
                        )),
                    )
                ).scalars().all()
                # Older ambiguous receipts appeared as unavailable in Chats.
                # Project their local status only when no acceptance was saved.
                connection.execute(update(response_records).where(
                    response_records.c.send_id.in_(uncertain_ids),
                    response_records.c.status.in_(("queued", "unavailable")),
                    response_records.c.accepted_at == 0,
                    response_records.c.conversation_id == "",
                ).values(status="outcome_unknown", updated_at=at, finished_at=at))
        except (OSError, SQLAlchemyError) as exc:
            logger.warning(
                "Accepted delivery reconciliation deferred error_type=%s",
                type(exc).__name__,
            )
            return 0
        if not confirmed_ids:
            return 0
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(job_deliveries)
                .where(
                    job_deliveries.c.send_id.in_(confirmed_ids),
                    job_deliveries.c.status == "outcome_unknown",
                )
                .values(
                    status="succeeded",
                    error="",
                    last_error="",
                    retry_at=0,
                    updated_at=at,
                    finished_at=case(
                        (job_deliveries.c.finished_at > 0, job_deliveries.c.finished_at),
                        else_=at,
                    ),
                )
            )
        return int(changed.rowcount or 0)

    def expire_leases(self, *, now: float | None = None) -> int:
        """Quarantine expired sends even while dispatch admission is blocked.

        Maintenance performs no send, retry or claim. Unproven outcomes stay
        quarantined; only a durable local acceptance receipt can resolve one.
        """
        at = time.time() if now is None else float(now)
        with self.engine.begin() as connection:
            expired_ids = self._expire_leases(connection, at)
        for send_id in expired_ids:
            self._mark_result_unavailable(send_id)
        reconciled = self.reconcile_accepted_outcomes(now=at)
        if reconciled:
            logger.info("Recovered %d durable accepted delivery receipts", reconciled)
        return len(expired_ids)

    @staticmethod
    def record_from_row(row: Mapping[str, object]) -> dict[str, object]:
        return {
            "send_id": str(row["send_id"]),
            "message": str(row["message"]),
            "images": image_refs(json.loads(str(row["images_json"] or "[]"))),
            "client_id": str(row["client_id"] or ""),
            "one_time": bool(row["one_time"]),
            "pin_chat": bool(row["pin_chat"]),
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

    def pending_once_deliveries(self) -> list[dict[str, object]]:
        """Unfinished immediate/manual and scheduled one-shot deliveries in claim order."""
        with self.engine.connect() as connection:
            rows = (
                connection.execute(
                    select(job_deliveries)
                    .where(
                        or_(
                            job_deliveries.c.client_id.like("manual:%"),
                            job_deliveries.c.one_time.is_(True),
                        ),
                        job_deliveries.c.status.in_(
                            ("queued", "retrying", "rate_limited", "running")
                        ),
                    )
                    .order_by(
                        job_deliveries.c.queue_priority,
                        _DISPATCH_PRIORITY,
                        job_deliveries.c.sequence,
                    )
                )
                .mappings()
                .all()
            )
        return [self.record_from_row(row) for row in rows]

    def bump_to_front(self, send_id: str) -> bool:
        """Prioritize a waiting delivery without changing retry or active leases."""
        priority = select(func.coalesce(func.min(job_deliveries.c.queue_priority), 0) - 1).scalar_subquery()
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(job_deliveries)
                .where(
                    job_deliveries.c.send_id == send_id,
                    job_deliveries.c.status.in_(("queued", "retrying", "rate_limited")),
                )
                .values(queue_priority=priority)
            )
        return bool(changed.rowcount)

    def pending_scheduled_send_ids(self) -> set[str]:
        """Unfinished scheduled delivery IDs, including removed one-shot definitions."""
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(job_deliveries.c.send_id).where(
                    job_deliveries.c.client_id.like("scheduled:%"),
                    job_deliveries.c.status.in_(
                        ("queued", "retrying", "rate_limited", "running")
                    ),
                )
            ).scalars().all()
        return {str(send_id) for send_id in rows}

    def pending_scheduled_deliveries(self) -> list[str]:
        """Queued scheduled job names in dispatch priority (no prompt content)."""
        with self.engine.connect() as connection:
            clients = connection.execute(
                select(job_deliveries.c.client_id)
                .where(
                    job_deliveries.c.client_id.like("scheduled:%"),
                    job_deliveries.c.status.in_(("queued", "retrying", "rate_limited")),
                )
                .order_by(job_deliveries.c.queue_priority, job_deliveries.c.one_time.desc(), job_deliveries.c.sequence)
            ).scalars().all()
        return [str(client).rsplit(":", 1)[-1] for client in clients]

    def pending_dispatch_metadata(self) -> list[dict[str, object]]:
        """Queued fresh-chat IDs in claim priority, without stored prompt bodies."""
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    job_deliveries.c.send_id,
                    job_deliveries.c.client_id,
                    job_deliveries.c.retry_at,
                    job_deliveries.c.one_time,
                )
                .where(job_deliveries.c.status.in_(("queued", "retrying", "rate_limited")))
                .order_by(job_deliveries.c.queue_priority, _DISPATCH_PRIORITY, job_deliveries.c.sequence)
            ).mappings().all()
        return [
            {
                "send_id": str(row["send_id"]),
                "client_id": str(row["client_id"]),
                "retry_at": float_value(row["retry_at"]),
                "one_time": bool(row["one_time"]),
            }
            for row in rows
        ]

    def active_delivery_send_ids(self, *, now: float) -> set[str]:
        """Count in-flight queue claims and all live chat/reply captures once each."""
        active = self.results.active_capture_send_ids(now=now)
        with self.engine.connect() as connection:
            running = connection.execute(
                select(job_deliveries.c.send_id).where(
                    job_deliveries.c.status == "running"
                )
            ).scalars().all()
        active.update(str(send_id) for send_id in running)
        return active

    def has_capacity(self, *, max_active: int | None, now: float | None = None) -> bool:
        """Advisory capacity check; the final claim always rechecks atomically."""
        if max_active is None:
            return True
        at = time.time() if now is None else float(now)
        return len(self.active_delivery_send_ids(now=at)) < max_active

    def claim_reply(
        self,
        store: ManualReplyStore,
        reply_id: str,
        owner: str,
        *,
        deadline: float,
        now: float | None = None,
        max_active: int | None = None,
    ) -> bool:
        """Claim a reply under the same SQLite writer mutex as fresh-chat claims.

        The lock on the fresh-chat queue serializes both paths, including across
        web and delivery-worker processes. Persist the reply lease before the
        queue transaction releases that lock.
        """
        if store.responses.path != self.results.path:
            raise ValueError("Reply and delivery stores must share a response database")
        at = time.time() if now is None else float(now)
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            running = set(str(send_id) for send_id in connection.execute(
                select(job_deliveries.c.send_id).where(job_deliveries.c.status == "running")
            ).scalars())
            active = self.results.active_capture_send_ids(now=at)
            if max_active is not None and len(running | active) >= max_active:
                return False
            return store.claim(reply_id, owner, deadline=deadline, now=at)

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
            next_retry = connection.execute(
                select(func.min(job_deliveries.c.retry_at)).where(
                    job_deliveries.c.status.in_(("retrying", "rate_limited")),
                    job_deliveries.c.retry_at > at,
                )
            ).scalar_one()
        count_by_status = {str(status): int(count) for status, count in counts}
        oldest = float(oldest_at or 0.0)
        return {
            "succeeded": count_by_status.get("succeeded", 0),
            "queued": count_by_status.get("queued", 0),
            "running": count_by_status.get("running", 0),
            "retrying": count_by_status.get("retrying", 0),
            "rate_limited": count_by_status.get("rate_limited", 0),
            "dead_lettered": count_by_status.get("dead_lettered", 0),
            "outcome_unknown": count_by_status.get("outcome_unknown", 0),
            "cancelled": count_by_status.get("cancelled", 0),
            "oldest_pending_age_seconds": max(0.0, at - oldest) if oldest else 0.0,
            "last_successful_delivery_at": float(last_success or 0.0),
            "next_retry_at_epoch": float(next_retry or 0.0),
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
                "images_json": json.dumps(image_refs(record.get("images", ()))),
                "client_id": client_id,
                "one_time": record.get("one_time") is True,
                "pin_chat": record.get("pin_chat") is True,
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
            receipt = self.record_from_row(row)
            created = result.rowcount == 1
        if created or receipt["status"] in ("queued", "running", "retrying", "rate_limited"):
            client = str(receipt["client_id"])
            job_name = (
                client.split(":", 2)[2]
                if client.startswith("scheduled:") and client.count(":") >= 2
                else ""
            )
            self.results.ensure_queued(
                str(receipt["send_id"]),
                str(receipt["message"]),
                job_name,
                now=float_value(receipt["created_at"]),
            )
        return receipt, created

    def enqueue_manual(
        self,
        prompt: str,
        *,
        now: float | None = None,
        pin_chat: bool = False,
        pin_local_default: bool = False,
        images: tuple[str, ...] = (),
        request_id: str | None = None,
    ) -> dict[str, object]:
        """Queue an independent fresh chat without touching any job's schedule."""
        if not prompt.strip():
            raise ValueError("Prompt is required")
        request_id = uuid.uuid4().hex if request_id is None else request_id
        if not re.fullmatch(r"[0-9a-f]{32}", request_id):
            raise ValueError("Invalid fresh chat request identifier")
        receipt, created = self.enqueue_idempotent(
            {
                "send_id": f"manual-{request_id}",
                "client_id": f"manual:{'once:' if pin_chat else ''}{request_id}",
                "pin_chat": pin_chat,
                "message": prompt,
                "images": images,
                "created_at": time.time() if now is None else now,
            }
        )
        initial_message_matches = receipt["message"] == prompt
        if not initial_message_matches:
            # Pending-chat follow-ups may have been merged into the first
            # delivery since the original fresh-chat HTTP acknowledgement.
            with self.results.engine.connect() as connection:
                original_hash = connection.execute(select(replies.c.message_id).where(
                    replies.c.send_id == receipt["send_id"],
                    replies.c.status == "merged",
                ).order_by(replies.c.created_at, replies.c.reply_id).limit(1)).scalar_one_or_none()
            initial_message_matches = original_hash == hashlib.sha256(prompt.encode()).hexdigest()
        if (
            not initial_message_matches
            or image_refs(receipt["images"]) != images
            or receipt["client_id"] != f"manual:{'once:' if pin_chat else ''}{request_id}"
        ):
            raise ValueError("Fresh chat identifier belongs to a different payload")
        if created and pin_local_default:
            # Prompta sidebar pins are distinct from ChatGPT account pins.
            # Do not re-pin a chat the user explicitly unpinned on a retry.
            self.results.set_local_pin(str(receipt["send_id"]), pinned=True)
        return receipt

    def promote_one_time(self, send_id: str) -> bool:
        """Restore priority for one-shot deliveries queued by an older release."""
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(job_deliveries)
                .where(
                    job_deliveries.c.send_id == send_id,
                    job_deliveries.c.one_time.is_(False),
                    job_deliveries.c.status.in_(("queued", "retrying", "rate_limited")),
                )
                .values(one_time=True)
            )
            return changed.rowcount == 1

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
            cancelled = result.rowcount == 1
        if cancelled:
            self._mark_result_unavailable(send_id)
        return cancelled

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
            "one_time": record.get("one_time") is True,
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
        if values["status"] in ("queued", "running", "retrying", "rate_limited"):
            client = str(values["client_id"])
            job_name = (
                client.split(":", 2)[2]
                if client.startswith("scheduled:") and client.count(":") >= 2
                else ""
            )
            self.results.ensure_queued(send_id, message, job_name, now=created)

    def claim_next(
        self,
        owner: str,
        *,
        lease_seconds: float,
        now: float | None = None,
        max_active: int | None = None,
    ) -> dict[str, object] | None:
        """Atomically claim one fresh chat only when a global slot is free.

        The queue remains durable even when the limit is full. Read the
        separately persisted capture receipts while holding the queue's write
        transaction: concurrent workers cannot both claim the final slot.
        """
        at = time.time() if now is None else float(now)
        with self.engine.begin() as connection:
            expired_ids = self._expire_leases(connection, at)
            running = set(
                str(send_id)
                for send_id in connection.execute(
                    select(job_deliveries.c.send_id).where(
                        job_deliveries.c.status == "running"
                    )
                ).scalars().all()
            )
            active = self.results.active_capture_send_ids(now=at)
            row = None
            if max_active is None or len(running | active) < max_active:
                claimable = or_(
                    (job_deliveries.c.status == "queued") & (job_deliveries.c.retry_at <= at),
                    job_deliveries.c.status.in_(RETRY_DELIVERY_STATUSES)
                    & (job_deliveries.c.retry_at <= at),
                )
                sequence = (
                    select(job_deliveries.c.sequence)
                    .where(claimable)
                    .order_by(job_deliveries.c.queue_priority, _DISPATCH_PRIORITY, job_deliveries.c.sequence)
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
        for expired_id in expired_ids:
            self._mark_result_unavailable(str(expired_id))
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
                    job_deliveries.c.lease_expires_at > at,
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
            # A stale owner cannot commit a send after its safety lease expires.
            if float_value(row["lease_expires_at"]) <= at:
                return False
            result = connection.execute(
                update(job_deliveries)
                .where(
                    job_deliveries.c.send_id == send_id,
                    job_deliveries.c.status == "running",
                    job_deliveries.c.lease_owner == owner,
                    job_deliveries.c.lease_expires_at > at,
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
                    job_deliveries.c.lease_expires_at > at,
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
            failed = result.rowcount == 1
        if failed:
            if status == "outcome_unknown":
                try:
                    self.results.uncertain(send_id)
                except (OSError, SQLAlchemyError) as exc:
                    logger.warning(
                        "Uncertain result projection deferred send_id=%s error_type=%s",
                        send_id, type(exc).__name__,
                    )
            else:
                self._mark_result_unavailable(send_id)
        return failed
