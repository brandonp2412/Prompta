from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

_TERMINAL_STATUSES = {"cancelled", "dead_lettered", "outcome_unknown", "succeeded"}
_RETRY_STATUSES = {"rate_limited", "retrying"}


class DeliveryQueueStore:
    """SQLite-backed delivery queue primitives safe for independent processes."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.initialize()

    def connect(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def initialize(self) -> None:
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS send_jobs (
                    sequence INTEGER PRIMARY KEY AUTOINCREMENT,
                    send_id TEXT NOT NULL UNIQUE,
                    operation TEXT NOT NULL,
                    message TEXT NOT NULL,
                    conversation_id TEXT NOT NULL DEFAULT '',
                    attachments_json TEXT NOT NULL DEFAULT '[]',
                    client_id TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL,
                    error TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    retry_at REAL NOT NULL DEFAULT 0,
                    retry_attempt INTEGER NOT NULL DEFAULT 0,
                    infrastructure_retry_attempt INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    finished_at REAL NOT NULL DEFAULT 0,
                    lease_owner TEXT NOT NULL DEFAULT '',
                    lease_acquired_at REAL NOT NULL DEFAULT 0,
                    lease_expires_at REAL NOT NULL DEFAULT 0
                )
                """
            )
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(send_jobs)").fetchall()
            }
            migrations = {
                "infrastructure_retry_attempt": "INTEGER NOT NULL DEFAULT 0",
                "lease_owner": "TEXT NOT NULL DEFAULT ''",
                "lease_acquired_at": "REAL NOT NULL DEFAULT 0",
                "lease_expires_at": "REAL NOT NULL DEFAULT 0",
            }
            for column, definition in migrations.items():
                if column not in columns:
                    connection.execute(f"ALTER TABLE send_jobs ADD COLUMN {column} {definition}")
            connection.execute(
                """
                CREATE UNIQUE INDEX IF NOT EXISTS send_jobs_client_id
                    ON send_jobs(client_id) WHERE client_id <> ''
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS send_jobs_fifo
                    ON send_jobs(status, sequence)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS send_jobs_claimable
                    ON send_jobs(status, retry_at, lease_expires_at, sequence)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS send_jobs_running_lease
                    ON send_jobs(lease_acquired_at, lease_expires_at)
                    WHERE status = 'running' AND lease_owner <> ''
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS send_jobs_succeeded_finished
                    ON send_jobs(finished_at DESC)
                    WHERE status = 'succeeded' AND finished_at > 0
                """
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def record_from_row(row: sqlite3.Row) -> dict[str, Any]:
        try:
            attachments = json.loads(str(row["attachments_json"] or "[]"))
        except (TypeError, ValueError):
            attachments = []
        keys = set(row.keys())
        record = {
            "sequence": int(row["sequence"]) if "sequence" in keys else 0,
            "send_id": str(row["send_id"]),
            "operation": str(row["operation"]),
            "message": str(row["message"]),
            "conversation_id": str(row["conversation_id"] or ""),
            "attachments": [value for value in attachments if isinstance(value, str)]
            if isinstance(attachments, list)
            else [],
            "client_id": str(row["client_id"] or ""),
            "status": str(row["status"]),
            "error": str(row["error"] or "") if "error" in keys else "",
            "retry_at": float(row["retry_at"] or 0.0),
            "retry_attempt": max(0, int(row["retry_attempt"] or 0)),
            "infrastructure_retry_attempt": max(0, int(row["infrastructure_retry_attempt"] or 0))
            if "infrastructure_retry_attempt" in keys
            else 0,
            "created_at": float(row["created_at"] or 0.0),
            "updated_at": float(row["updated_at"] or 0.0) if "updated_at" in keys else 0.0,
            "lease_owner": str(row["lease_owner"] or "") if "lease_owner" in keys else "",
            "lease_acquired_at": (
                float(row["lease_acquired_at"] or 0.0) if "lease_acquired_at" in keys else 0.0
            ),
            "lease_expires_at": (
                float(row["lease_expires_at"] or 0.0) if "lease_expires_at" in keys else 0.0
            ),
        }
        last_error = str(row["last_error"] or "")
        if last_error:
            record["last_error"] = last_error
        finished_at = float(row["finished_at"] or 0.0)
        if finished_at > 0:
            record["finished_at"] = finished_at
        return record

    def records(self) -> list[dict[str, Any]]:
        connection = self.connect()
        try:
            rows = connection.execute("SELECT * FROM send_jobs ORDER BY sequence").fetchall()
            return [self.record_from_row(row) for row in rows]
        finally:
            connection.close()

    def health_metrics(self, *, now: float | None = None) -> dict[str, Any]:
        current = time.time() if now is None else float(now)
        connection = self.connect()
        try:
            ready = connection.execute(
                """
                SELECT MIN(created_at) AS oldest_ready_at
                FROM send_jobs
                WHERE status = 'queued'
                   OR (
                       status IN ('retrying', 'rate_limited')
                       AND retry_at <= ?
                   )
                   OR (
                       status = 'running'
                       AND lease_expires_at <= ?
                   )
                """,
                (current, current),
            ).fetchone()
            lease = connection.execute(
                """
                SELECT send_id, lease_owner, lease_acquired_at, lease_expires_at
                FROM send_jobs
                WHERE status = 'running'
                  AND lease_owner <> ''
                  AND lease_expires_at > ?
                ORDER BY lease_acquired_at
                LIMIT 1
                """,
                (current,),
            ).fetchone()
            success = connection.execute(
                """
                SELECT send_id, conversation_id, finished_at
                FROM send_jobs
                WHERE status = 'succeeded'
                  AND finished_at > 0
                ORDER BY finished_at DESC
                LIMIT 1
                """
            ).fetchone()
        finally:
            connection.close()

        oldest_ready_at = float(ready["oldest_ready_at"] or 0.0) if ready is not None else 0.0
        lease_acquired_at = float(lease["lease_acquired_at"] or 0.0) if lease is not None else 0.0
        last_success_at = float(success["finished_at"] or 0.0) if success is not None else 0.0
        return {
            "oldest_ready_at": oldest_ready_at,
            "oldest_ready_age_seconds": (
                max(0.0, current - oldest_ready_at) if oldest_ready_at > 0 else None
            ),
            "current_lease_send_id": str(lease["send_id"] or "") if lease is not None else "",
            "current_lease_owner": str(lease["lease_owner"] or "") if lease is not None else "",
            "current_lease_acquired_at": lease_acquired_at,
            "current_lease_expires_at": (
                float(lease["lease_expires_at"] or 0.0) if lease is not None else 0.0
            ),
            "current_lease_age_seconds": (
                max(0.0, current - lease_acquired_at) if lease_acquired_at > 0 else None
            ),
            "last_successful_delivery_at": last_success_at,
            "last_successful_delivery_send_id": (
                str(success["send_id"] or "") if success is not None else ""
            ),
            "last_successful_delivery_conversation_id": (
                str(success["conversation_id"] or "") if success is not None else ""
            ),
        }

    def get(self, send_id: str) -> dict[str, Any] | None:
        connection = self.connect()
        try:
            row = connection.execute(
                "SELECT * FROM send_jobs WHERE send_id = ?",
                (send_id,),
            ).fetchone()
            return self.record_from_row(row) if row is not None else None
        finally:
            connection.close()

    def enqueue_idempotent(self, record: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        """Insert a delivery exactly once without changing an existing receipt."""
        send_id = str(record["send_id"])
        client_id = str(record.get("client_id") or "")
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT * FROM send_jobs WHERE send_id = ?",
                (send_id,),
            ).fetchone()
            if row is None and client_id:
                row = connection.execute(
                    "SELECT * FROM send_jobs WHERE client_id = ?",
                    (client_id,),
                ).fetchone()
            if row is not None:
                connection.commit()
                return self.record_from_row(row), False

            now = time.time()
            connection.execute(
                """
                INSERT INTO send_jobs (
                    send_id, operation, message, conversation_id, attachments_json,
                    client_id, status, error, created_at, updated_at, retry_at,
                    retry_attempt, last_error, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    send_id,
                    str(record["operation"]),
                    str(record["message"]),
                    str(record.get("conversation_id") or ""),
                    json.dumps(record.get("attachments", [])),
                    client_id,
                    str(record.get("status") or "queued"),
                    str(record.get("error") or ""),
                    float(record.get("created_at") or now),
                    float(record.get("updated_at") or now),
                    float(record.get("retry_at") or 0.0),
                    max(0, int(record.get("retry_attempt") or 0)),
                    str(record.get("last_error") or ""),
                    float(record.get("finished_at") or 0.0),
                ),
            )
            row = connection.execute(
                "SELECT * FROM send_jobs WHERE send_id = ?",
                (send_id,),
            ).fetchone()
            connection.commit()
            if row is None:
                raise sqlite3.DatabaseError("delivery enqueue did not persist a row")
            return self.record_from_row(row), True
        finally:
            connection.close()

    def requeue_legacy_outage(self, send_id: str, expected_error: str) -> bool:
        """Requeue only the unchanged legacy failure; never overwrite a newer receipt."""
        connection = self.connect()
        try:
            updated = connection.execute(
                """
                UPDATE send_jobs
                SET status = 'queued', error = '', last_error = '', retry_at = 0,
                    retry_attempt = 0, finished_at = 0, updated_at = ?
                WHERE send_id = ? AND status = 'dead_lettered' AND last_error = ?
                """,
                (time.time(), send_id, expected_error),
            )
            connection.commit()
            return updated.rowcount == 1
        finally:
            connection.close()

    def upsert(self, record: dict[str, Any]) -> None:
        connection = self.connect()
        try:
            connection.execute(
                """
                INSERT INTO send_jobs (
                    send_id, operation, message, conversation_id, attachments_json,
                    client_id, status, error, created_at, updated_at, retry_at,
                    retry_attempt, last_error, finished_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(send_id) DO UPDATE SET
                    operation=excluded.operation,
                    message=excluded.message,
                    conversation_id=excluded.conversation_id,
                    attachments_json=excluded.attachments_json,
                    client_id=excluded.client_id,
                    status=excluded.status,
                    error=excluded.error,
                    updated_at=excluded.updated_at,
                    retry_at=excluded.retry_at,
                    retry_attempt=excluded.retry_attempt,
                    last_error=excluded.last_error,
                    finished_at=excluded.finished_at
                """,
                (
                    record["send_id"],
                    record["operation"],
                    record["message"],
                    record.get("conversation_id", ""),
                    json.dumps(record.get("attachments", [])),
                    record.get("client_id", ""),
                    record.get("status", "queued"),
                    record.get("error", record.get("last_error", "")),
                    float(record.get("created_at") or time.time()),
                    float(record.get("updated_at") or time.time()),
                    float(record.get("retry_at") or 0.0),
                    max(0, int(record.get("retry_attempt") or 0)),
                    record.get("last_error", ""),
                    float(record.get("finished_at") or 0.0),
                ),
            )
            connection.commit()
        finally:
            connection.close()

    def delete(self, send_id: str) -> None:
        connection = self.connect()
        try:
            connection.execute("DELETE FROM send_jobs WHERE send_id = ?", (send_id,))
            connection.commit()
        finally:
            connection.close()

    def bump(self, send_id: str) -> None:
        connection = self.connect()
        try:
            connection.execute(
                """
                UPDATE send_jobs
                SET sequence = (SELECT COALESCE(MIN(sequence), 0) - 1 FROM send_jobs)
                WHERE send_id = ?
                  AND status IN ('queued', 'retrying', 'rate_limited')
                """,
                (send_id,),
            )
            connection.commit()
        finally:
            connection.close()

    def claim_next(
        self,
        owner: str,
        *,
        now: float | None = None,
        lease_seconds: float = 90.0,
    ) -> dict[str, Any] | None:
        if not owner:
            raise ValueError("delivery claim owner must not be empty")
        claim_time = time.time() if now is None else float(now)
        lease_expires_at = claim_time + max(1.0, float(lease_seconds))
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT send_id
                FROM send_jobs
                WHERE status = 'queued'
                   OR (
                       status IN ('retrying', 'rate_limited')
                       AND retry_at <= ?
                   )
                   OR (
                       status = 'running'
                       AND lease_expires_at <= ?
                   )
                ORDER BY sequence
                LIMIT 1
                """,
                (claim_time, claim_time),
            ).fetchone()
            if row is None:
                connection.commit()
                return None
            send_id = str(row["send_id"])
            updated = connection.execute(
                """
                UPDATE send_jobs
                SET status = 'running',
                    lease_owner = ?,
                    lease_acquired_at = ?,
                    lease_expires_at = ?,
                    updated_at = ?
                WHERE send_id = ?
                  AND (
                      status = 'queued'
                      OR (
                          status IN ('retrying', 'rate_limited')
                          AND retry_at <= ?
                      )
                      OR (
                          status = 'running'
                          AND lease_expires_at <= ?
                      )
                  )
                """,
                (
                    owner,
                    claim_time,
                    lease_expires_at,
                    claim_time,
                    send_id,
                    claim_time,
                    claim_time,
                ),
            )
            if updated.rowcount != 1:
                connection.rollback()
                return None
            claimed = connection.execute(
                "SELECT * FROM send_jobs WHERE send_id = ?",
                (send_id,),
            ).fetchone()
            connection.commit()
            return self.record_from_row(claimed) if claimed is not None else None
        finally:
            connection.close()

    def renew_lease(
        self,
        send_id: str,
        owner: str,
        *,
        now: float | None = None,
        lease_seconds: float = 90.0,
    ) -> bool:
        renew_time = time.time() if now is None else float(now)
        lease_expires_at = renew_time + max(1.0, float(lease_seconds))
        connection = self.connect()
        try:
            updated = connection.execute(
                """
                UPDATE send_jobs
                SET lease_expires_at = ?,
                    updated_at = ?
                WHERE send_id = ?
                  AND status = 'running'
                  AND lease_owner = ?
                  AND lease_expires_at > ?
                """,
                (lease_expires_at, renew_time, send_id, owner, renew_time),
            )
            connection.commit()
            return updated.rowcount == 1
        finally:
            connection.close()

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
        if status not in _RETRY_STATUSES:
            raise ValueError(f"unsupported retry status: {status}")
        update_time = time.time() if now is None else float(now)
        connection = self.connect()
        try:
            updated = connection.execute(
                """
                UPDATE send_jobs
                SET status = ?,
                    error = ?,
                    last_error = ?,
                    retry_at = ?,
                    retry_attempt = ?,
                    updated_at = ?,
                    lease_owner = '',
                    lease_acquired_at = 0,
                    lease_expires_at = 0
                WHERE send_id = ?
                  AND status = 'running'
                  AND lease_owner = ?
                """,
                (
                    status,
                    error,
                    error,
                    float(retry_at),
                    max(0, int(retry_attempt)),
                    update_time,
                    send_id,
                    owner,
                ),
            )
            connection.commit()
            return updated.rowcount == 1
        finally:
            connection.close()

    def complete_claim(
        self,
        send_id: str,
        owner: str,
        *,
        conversation_id: str,
        now: float | None = None,
    ) -> bool:
        completed_at = time.time() if now is None else float(now)
        connection = self.connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT status, lease_owner, conversation_id
                FROM send_jobs
                WHERE send_id = ?
                """,
                (send_id,),
            ).fetchone()
            if row is None:
                connection.commit()
                return False
            status = str(row["status"])
            if status == "succeeded":
                connection.commit()
                return True
            if status in _TERMINAL_STATUSES or status != "running":
                connection.commit()
                return False
            if str(row["lease_owner"] or "") != owner:
                connection.commit()
                return False
            connection.execute(
                """
                UPDATE send_jobs
                SET status = 'succeeded',
                    conversation_id = ?,
                    error = '',
                    last_error = '',
                    retry_at = 0,
                    finished_at = CASE WHEN finished_at > 0 THEN finished_at ELSE ? END,
                    updated_at = ?,
                    lease_owner = '',
                    lease_acquired_at = 0,
                    lease_expires_at = 0
                WHERE send_id = ?
                  AND status = 'running'
                  AND lease_owner = ?
                """,
                (conversation_id, completed_at, completed_at, send_id, owner),
            )
            connection.commit()
            return True
        finally:
            connection.close()
