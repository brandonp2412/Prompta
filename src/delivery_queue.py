from __future__ import annotations

import sqlite3
import time
from pathlib import Path
from typing import Any

from .delivery_state import (
    RETRY_DELIVERY_STATUSES,
    TERMINAL_DELIVERY_STATUSES,
    CompletionAction,
    claimable_delivery,
    completion_action,
    owned_running_delivery,
    renewable_delivery_lease,
)


class DeliveryQueueStore:
    """SQLite-backed queue containing only scheduled fresh-chat job deliveries."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def initialize(self) -> None:
        with self.connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS job_deliveries (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    send_id TEXT NOT NULL UNIQUE,
                    message TEXT NOT NULL,
                    client_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    error TEXT NOT NULL DEFAULT '',
                    last_error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    retry_at REAL NOT NULL DEFAULT 0,
                    retry_attempt INTEGER NOT NULL DEFAULT 0,
                    finished_at REAL NOT NULL DEFAULT 0,
                    lease_owner TEXT NOT NULL DEFAULT '',
                    lease_acquired_at REAL NOT NULL DEFAULT 0,
                    lease_expires_at REAL NOT NULL DEFAULT 0
                )
                """
            )
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS job_deliveries_client_id
                ON job_deliveries(client_id) WHERE client_id <> ''
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS job_deliveries_claimable
                ON job_deliveries(status, retry_at, lease_expires_at, sequence)
                """
            )


    @staticmethod
    def record_from_row(row: sqlite3.Row) -> dict[str, Any]:
        return {
            "send_id": str(row["send_id"]),
            "message": str(row["message"]),
            "client_id": str(row["client_id"] or ""),
            "status": str(row["status"] or "queued"),
            "error": str(row["error"] or ""),
            "last_error": str(row["last_error"] or ""),
            "created_at": float(row["created_at"] or 0.0),
            "updated_at": float(row["updated_at"] or 0.0),
            "retry_at": float(row["retry_at"] or 0.0),
            "retry_attempt": int(row["retry_attempt"] or 0),
            "finished_at": float(row["finished_at"] or 0.0),
            "lease_owner": str(row["lease_owner"] or ""),
            "lease_acquired_at": float(row["lease_acquired_at"] or 0.0),
            "lease_expires_at": float(row["lease_expires_at"] or 0.0),
        }

    def records(self) -> list[dict[str, Any]]:
        with self.connect() as connection:
            rows = connection.execute("SELECT * FROM job_deliveries ORDER BY sequence").fetchall()
        return [self.record_from_row(row) for row in rows]

    def health_metrics(self, *, now: float | None = None) -> dict[str, Any]:
        at = time.time() if now is None else float(now)
        with self.connect() as connection:
            counts = {
                str(row["status"]): int(row["count"])
                for row in connection.execute(
                    """
                    SELECT status, COUNT(*) AS count
                    FROM job_deliveries
                    GROUP BY status
                    """
                ).fetchall()
            }
            oldest = connection.execute(
                """
                SELECT MIN(created_at) AS created_at
                FROM job_deliveries
                WHERE status IN ('queued', 'retrying', 'rate_limited', 'running')
                """
            ).fetchone()
            success = connection.execute(
                """
                SELECT finished_at
                FROM job_deliveries
                WHERE status = 'succeeded'
                ORDER BY finished_at DESC
                LIMIT 1
                """
            ).fetchone()

        oldest_at = float(oldest["created_at"] or 0.0) if oldest is not None else 0.0
        return {
            "queued": counts.get("queued", 0),
            "running": counts.get("running", 0),
            "retrying": counts.get("retrying", 0),
            "rate_limited": counts.get("rate_limited", 0),
            "dead_lettered": counts.get("dead_lettered", 0),
            "outcome_unknown": counts.get("outcome_unknown", 0),
            "oldest_pending_age_seconds": max(0.0, at - oldest_at) if oldest_at else 0.0,
            "last_successful_delivery_at": (
                float(success["finished_at"] or 0.0) if success is not None else 0.0
            ),
        }

    def get(self, send_id: str) -> dict[str, Any] | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT * FROM job_deliveries WHERE send_id = ?",
                (send_id,),
            ).fetchone()
        return self.record_from_row(row) if row is not None else None

    def enqueue_idempotent(self, record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        send_id = str(record.get("send_id") or "")
        message = str(record.get("message") or "")
        client_id = str(record.get("client_id") or "")
        if not send_id:
            raise ValueError("delivery send_id is required")
        if not message:
            raise ValueError("delivery message is required")

        now = float(record.get("created_at") or time.time())
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT * FROM job_deliveries WHERE send_id = ?",
                (send_id,),
            ).fetchone()
            if existing is None and client_id:
                existing = connection.execute(
                    "SELECT * FROM job_deliveries WHERE client_id = ?",
                    (client_id,),
                ).fetchone()
            if existing is not None:
                connection.commit()
                return self.record_from_row(existing), False

            connection.execute(
                """
                INSERT INTO job_deliveries(
                    send_id, message, client_id, status, error, last_error,
                    created_at, updated_at, retry_at, retry_attempt, finished_at
                )
                VALUES (?, ?, ?, 'queued', '', '', ?, ?, 0, 0, 0)
                """,
                (send_id, message, client_id, now, now),
            )
            row = connection.execute(
                "SELECT * FROM job_deliveries WHERE send_id = ?",
                (send_id,),
            ).fetchone()
            connection.commit()
        assert row is not None
        return self.record_from_row(row), True

    def upsert(self, record: dict[str, Any]) -> None:
        send_id = str(record.get("send_id") or "")
        message = str(record.get("message") or "")
        if not send_id:
            raise ValueError("delivery send_id is required")
        if not message:
            raise ValueError("delivery message is required")

        created_at = float(record.get("created_at") or time.time())
        updated_at = float(record.get("updated_at") or created_at)
        values = (
            send_id,
            message,
            str(record.get("client_id") or ""),
            str(record.get("status") or "queued"),
            str(record.get("error") or ""),
            str(record.get("last_error") or ""),
            created_at,
            updated_at,
            float(record.get("retry_at") or 0.0),
            int(record.get("retry_attempt") or 0),
            float(record.get("finished_at") or 0.0),
            str(record.get("lease_owner") or ""),
            float(record.get("lease_acquired_at") or 0.0),
            float(record.get("lease_expires_at") or 0.0),
        )
        with self.connect() as connection:
            connection.execute(
                """
                INSERT INTO job_deliveries(
                    send_id, message, client_id, status, error, last_error,
                    created_at, updated_at, retry_at, retry_attempt, finished_at,
                    lease_owner, lease_acquired_at, lease_expires_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(send_id) DO UPDATE SET
                    message = excluded.message,
                    client_id = excluded.client_id,
                    status = excluded.status,
                    error = excluded.error,
                    last_error = excluded.last_error,
                    created_at = excluded.created_at,
                    updated_at = excluded.updated_at,
                    retry_at = excluded.retry_at,
                    retry_attempt = excluded.retry_attempt,
                    finished_at = excluded.finished_at,
                    lease_owner = excluded.lease_owner,
                    lease_acquired_at = excluded.lease_acquired_at,
                    lease_expires_at = excluded.lease_expires_at
                """,
                values,
            )

    def claim_next(
        self,
        owner: str,
        *,
        lease_seconds: float,
        now: float | None = None,
    ) -> dict[str, Any] | None:
        claimed_at = time.time() if now is None else float(now)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            rows = connection.execute(
                """
                SELECT *
                FROM job_deliveries
                WHERE status IN ('queued', 'retrying', 'rate_limited', 'running')
                ORDER BY sequence
                """
            ).fetchall()
            row = next(
                (
                    candidate
                    for candidate in rows
                    if claimable_delivery(self.record_from_row(candidate), now=claimed_at)
                ),
                None,
            )
            if row is None:
                connection.commit()
                return None

            send_id = str(row["send_id"])
            connection.execute(
                """
                UPDATE job_deliveries
                SET status = 'running',
                    updated_at = ?,
                    lease_owner = ?,
                    lease_acquired_at = ?,
                    lease_expires_at = ?
                WHERE send_id = ?
                """,
                (
                    claimed_at,
                    owner,
                    claimed_at,
                    claimed_at + max(1.0, float(lease_seconds)),
                    send_id,
                ),
            )
            claimed = connection.execute(
                "SELECT * FROM job_deliveries WHERE send_id = ?",
                (send_id,),
            ).fetchone()
            connection.commit()
        return self.record_from_row(claimed) if claimed is not None else None

    def renew_lease(
        self,
        send_id: str,
        owner: str,
        *,
        lease_seconds: float,
        now: float | None = None,
    ) -> bool:
        renewed_at = time.time() if now is None else float(now)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM job_deliveries WHERE send_id = ?",
                (send_id,),
            ).fetchone()
            if row is None or not renewable_delivery_lease(
                self.record_from_row(row),
                owner=owner,
                now=renewed_at,
            ):
                connection.commit()
                return False
            updated = connection.execute(
                """
                UPDATE job_deliveries
                SET updated_at = ?, lease_expires_at = ?
                WHERE send_id = ?
                """,
                (renewed_at, renewed_at + max(1.0, float(lease_seconds)), send_id),
            )
            connection.commit()
            return updated.rowcount == 1

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
        update_time = time.time() if now is None else float(now)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM job_deliveries WHERE send_id = ?",
                (send_id,),
            ).fetchone()
            if row is None or not owned_running_delivery(self.record_from_row(row), owner=owner):
                connection.commit()
                return False
            updated = connection.execute(
                """
                UPDATE job_deliveries
                SET status = ?, error = ?, last_error = ?, retry_at = ?,
                    retry_attempt = ?, updated_at = ?,
                    lease_owner = '', lease_acquired_at = 0, lease_expires_at = 0
                WHERE send_id = ?
                """,
                (
                    status,
                    error,
                    error,
                    float(retry_at),
                    max(0, int(retry_attempt)),
                    update_time,
                    send_id,
                ),
            )
            connection.commit()
            return updated.rowcount == 1

    def complete_claim(
        self,
        send_id: str,
        owner: str,
        *,
        now: float | None = None,
    ) -> bool:
        completed_at = time.time() if now is None else float(now)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM job_deliveries WHERE send_id = ?",
                (send_id,),
            ).fetchone()
            if row is None:
                connection.commit()
                return False
            action = completion_action(self.record_from_row(row), owner=owner)
            if action is CompletionAction.ACKNOWLEDGE:
                connection.commit()
                return True
            if action is CompletionAction.REJECT:
                connection.commit()
                return False
            updated = connection.execute(
                """
                UPDATE job_deliveries
                SET status = 'succeeded', error = '', last_error = '', retry_at = 0,
                    finished_at = CASE WHEN finished_at > 0 THEN finished_at ELSE ? END,
                    updated_at = ?, lease_owner = '', lease_acquired_at = 0,
                    lease_expires_at = 0
                WHERE send_id = ?
                """,
                (completed_at, completed_at, send_id),
            )
            connection.commit()
            return updated.rowcount == 1

    def fail_claim(
        self,
        send_id: str,
        owner: str,
        *,
        status: str,
        error: str,
        now: float | None = None,
    ) -> bool:
        if status not in TERMINAL_DELIVERY_STATUSES or status == "succeeded":
            raise ValueError(f"unsupported terminal delivery status: {status}")
        finished_at = time.time() if now is None else float(now)
        with self.connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM job_deliveries WHERE send_id = ?",
                (send_id,),
            ).fetchone()
            if row is None or not owned_running_delivery(self.record_from_row(row), owner=owner):
                connection.commit()
                return False
            updated = connection.execute(
                """
                UPDATE job_deliveries
                SET status = ?, error = ?, last_error = ?, retry_at = 0,
                    finished_at = ?, updated_at = ?, lease_owner = '',
                    lease_acquired_at = 0, lease_expires_at = 0
                WHERE send_id = ?
                """,
                (status, error, error, finished_at, finished_at, send_id),
            )
            connection.commit()
            return updated.rowcount == 1
