from __future__ import annotations

import json
import logging
import math
import sqlite3
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .control_server import ControlDeferredError, ControlUnavailableError
from .rate_limit import (
    DEFAULT_RETRY_AFTER,
    RateLimitBackoff,
    RateLimitError,
    is_rate_limited_text,
    parse_retry_after,
)

logger = logging.getLogger(__name__)

_SEND_RETRY_BASE_SECONDS = 2.0
_SEND_RETRY_CAP_SECONDS = 60.0
_SEND_RETRY_MAX_ATTEMPTS = 5
_DEAD_LETTER_LIMIT = 100
_SUCCEEDED_RECEIPT_LIMIT = 1000
_LEGACY_PRE_SEND_OUTAGE_ERRORS = (
    "Prompta scheduler is running but its control socket is unavailable:",
    "Prompta backend is unavailable after starting prompta.service",
)


def _is_legacy_pre_send_outage(error: str) -> bool:
    message = error.strip()
    return any(message.startswith(prefix) for prefix in _LEGACY_PRE_SEND_OUTAGE_ERRORS)


class SendJobRegistry:
    """Run UI sends off-request and expose their status for polling."""

    @staticmethod
    def _cleanup_attachments(attachments: list[str]) -> None:
        for attachment in attachments:
            try:
                Path(attachment).unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove Prompta UI upload %s", attachment, exc_info=True)

    def __init__(
        self,
        sender: Callable[[str, str, str, list[str]], str],
        *,
        sleeper: Callable[[float], None] = time.sleep,
        recovery_path: Path | None = None,
        queue_path: Path | None = None,
        on_success: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._sender = sender
        self._sleep = sleeper
        self._on_success = on_success
        self._jobs: dict[str, dict[str, Any]] = {}
        self._client_jobs: dict[str, str] = {}
        self._lock = threading.Lock()
        self._work_event = threading.Event()
        self._fallback_tasks: list[tuple[str, str, str, str, list[str], str]] = []
        self._rate_limit_lock = threading.Lock()
        self._rate_limit_backoff = RateLimitBackoff()
        self._revision = 0
        self._recovery_path = recovery_path
        self._queue_path = queue_path or (
            recovery_path.with_name("ui-send-jobs.sqlite3") if recovery_path else None
        )
        self._recovery_lock = threading.Lock()
        self._recoverable: dict[str, dict[str, Any]] = {}
        self._cancelled: set[str] = set()
        self._initialize_database()
        self._restore_recoverable()
        self._worker = threading.Thread(
            target=self._worker_loop,
            name="prompta-ui-send-worker",
            daemon=True,
        )
        self._worker.start()

    def _connect_database(self) -> sqlite3.Connection | None:
        if self._queue_path is None:
            return None
        self._queue_path.parent.mkdir(parents=True, exist_ok=True)
        connection = sqlite3.connect(self._queue_path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=FULL")
        connection.execute("PRAGMA busy_timeout=30000")
        return connection

    def _initialize_database(self) -> None:
        connection = self._connect_database()
        if connection is None:
            return
        try:
            connection.executescript(
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
                    last_error TEXT NOT NULL DEFAULT '',
                    finished_at REAL NOT NULL DEFAULT 0
                );
                CREATE UNIQUE INDEX IF NOT EXISTS send_jobs_client_id
                    ON send_jobs(client_id) WHERE client_id <> '';
                CREATE INDEX IF NOT EXISTS send_jobs_fifo
                    ON send_jobs(status, sequence);
                """
            )
            connection.commit()
        finally:
            connection.close()

    @staticmethod
    def _record_from_row(row: sqlite3.Row) -> dict[str, Any]:
        try:
            attachments = json.loads(str(row["attachments_json"] or "[]"))
        except (TypeError, ValueError):
            attachments = []
        record = {
            "send_id": str(row["send_id"]),
            "operation": str(row["operation"]),
            "message": str(row["message"]),
            "conversation_id": str(row["conversation_id"] or ""),
            "attachments": [value for value in attachments if isinstance(value, str)]
            if isinstance(attachments, list)
            else [],
            "client_id": str(row["client_id"] or ""),
            "status": str(row["status"]),
            "retry_at": float(row["retry_at"] or 0.0),
            "retry_attempt": max(0, int(row["retry_attempt"] or 0)),
            "created_at": float(row["created_at"] or 0.0),
        }
        last_error = str(row["last_error"] or "")
        if last_error:
            record["last_error"] = last_error
        finished_at = float(row["finished_at"] or 0.0)
        if finished_at > 0:
            record["finished_at"] = finished_at
        return record

    def _database_records(self) -> list[dict[str, Any]]:
        connection = self._connect_database()
        if connection is None:
            return []
        try:
            rows = connection.execute("SELECT * FROM send_jobs ORDER BY sequence").fetchall()
            return [self._record_from_row(row) for row in rows]
        finally:
            connection.close()

    def _upsert_database_record(self, record: dict[str, Any]) -> None:
        connection = self._connect_database()
        if connection is None:
            return
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

    def _delete_database_record(self, send_id: str) -> None:
        connection = self._connect_database()
        if connection is None:
            return
        try:
            connection.execute("DELETE FROM send_jobs WHERE send_id = ?", (send_id,))
            connection.commit()
        finally:
            connection.close()

    def _bump_database_record(self, send_id: str) -> None:
        connection = self._connect_database()
        if connection is None:
            return
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

    def _worker_loop(self) -> None:
        while True:
            task = self._next_database_task()
            if task is None:
                self._work_event.wait(timeout=1.0)
                self._work_event.clear()
                continue
            try:
                self._run(*task)
            except Exception:
                logger.exception("Prompta UI send worker failed")

    def _next_database_task(
        self,
    ) -> tuple[str, str, str, str, list[str], str] | None:
        connection = self._connect_database()
        if connection is None:
            with self._lock:
                return self._fallback_tasks.pop(0) if self._fallback_tasks else None
        try:
            row = connection.execute(
                """
                SELECT * FROM send_jobs
                WHERE status = 'queued'
                   OR (
                       status IN ('retrying', 'rate_limited')
                       AND retry_at <= ?
                   )
                ORDER BY sequence
                LIMIT 1
                """,
                (time.time(),),
            ).fetchone()
            if row is None:
                return None
            record = self._record_from_row(row)
            return (
                record["send_id"],
                record["operation"],
                record["message"],
                record["conversation_id"],
                record["attachments"],
                record["client_id"],
            )
        finally:
            connection.close()

    def _write_recovery_locked(self) -> None:
        # Durable recovery lives in the send_jobs SQLite table. The JSON path is
        # retained only long enough to import installations from older Prompta.
        path = self._recovery_path
        if path is not None:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not remove legacy Prompta retry JSON %s", path, exc_info=True)

    def _remember_recoverable(
        self,
        *,
        send_id: str,
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str],
        client_id: str,
        created_at: float,
        status: str = "queued",
        retry_at: float = 0.0,
        retry_attempt: int = 0,
        last_error: str = "",
        finished_at: float = 0.0,
    ) -> None:
        if self._queue_path is None:
            return
        record = {
            "send_id": send_id,
            "operation": operation,
            "message": message,
            "conversation_id": conversation_id,
            "attachments": attachments,
            "client_id": client_id,
            "status": status,
            "retry_at": retry_at,
            "retry_attempt": retry_attempt,
            "created_at": created_at,
        }
        if last_error:
            record["last_error"] = last_error
        if finished_at > 0:
            record["finished_at"] = finished_at
        self._upsert_database_record(record)
        expired_attachments: list[str] = []
        expired_ids: list[str] = []
        retained_attachments: set[str] = set()
        with self._recovery_lock:
            self._recoverable[send_id] = record
            if status == "dead_lettered":
                dead_letters = sorted(
                    (
                        (key, value)
                        for key, value in self._recoverable.items()
                        if value.get("status") == "dead_lettered"
                    ),
                    key=lambda item: float(item[1].get("created_at") or 0.0),
                )
                for expired_id, expired_record in dead_letters[:-_DEAD_LETTER_LIMIT]:
                    self._recoverable.pop(expired_id, None)
                    expired_ids.append(expired_id)
                    raw_attachments = expired_record.get("attachments", [])
                    if isinstance(raw_attachments, list):
                        expired_attachments.extend(
                            value for value in raw_attachments if isinstance(value, str)
                        )
            elif status == "succeeded":
                succeeded = sorted(
                    (
                        (key, value)
                        for key, value in self._recoverable.items()
                        if value.get("status") == "succeeded"
                    ),
                    key=lambda item: float(
                        item[1].get("finished_at") or item[1].get("created_at") or 0.0
                    ),
                )
                for expired_id, expired_record in succeeded[:-_SUCCEEDED_RECEIPT_LIMIT]:
                    self._recoverable.pop(expired_id, None)
                    expired_ids.append(expired_id)
                    raw_attachments = expired_record.get("attachments", [])
                    if isinstance(raw_attachments, list):
                        expired_attachments.extend(
                            value for value in raw_attachments if isinstance(value, str)
                        )
            if status in {"cancelled", "dead_lettered", "succeeded"}:
                retained_attachments = {
                    value
                    for recoverable in self._recoverable.values()
                    for value in (
                        recoverable.get("attachments", [])
                        if isinstance(recoverable.get("attachments"), list)
                        else []
                    )
                    if isinstance(value, str)
                }
            self._write_recovery_locked()
        for expired_id in expired_ids:
            self._delete_database_record(expired_id)
        if expired_attachments:
            self._cleanup_attachments(
                [
                    attachment
                    for attachment in expired_attachments
                    if attachment not in retained_attachments
                ]
            )

    def _forget_recoverable(self, send_id: str) -> None:
        self._delete_database_record(send_id)
        if self._queue_path is None:
            return
        with self._recovery_lock:
            if self._recoverable.pop(send_id, None) is not None:
                self._write_recovery_locked()

    def _restore_recoverable(self) -> None:
        path = self._recovery_path
        records = self._database_records()
        if not records and path is not None and path.exists():
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                legacy_records = payload.get("jobs", []) if isinstance(payload, dict) else []
                records = legacy_records if isinstance(legacy_records, list) else []
                for record in records:
                    if isinstance(record, dict):
                        self._upsert_database_record(record)
                path.unlink(missing_ok=True)
            except (OSError, ValueError):
                logger.warning("Could not restore Prompta UI retry state %s", path, exc_info=True)
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
                return
        elif records and path is not None and path.exists():
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning(
                    "Could not remove legacy Prompta UI retry state %s", path, exc_info=True
                )
        if not records:
            return

        now = time.time()
        max_retry_at = 0.0
        max_attempt = 0
        restored: list[dict[str, Any]] = []
        for candidate in records:
            if not isinstance(candidate, dict):
                continue
            send_id = str(candidate.get("send_id") or "")
            operation = str(candidate.get("operation") or "")
            message = str(candidate.get("message") or "")
            conversation_id = str(candidate.get("conversation_id") or "")
            client_id = str(candidate.get("client_id") or "")
            raw_attachments = candidate.get("attachments", [])
            attachments = (
                [str(value) for value in raw_attachments if isinstance(value, str)]
                if isinstance(raw_attachments, list)
                else []
            )
            try:
                retry_at = float(candidate.get("retry_at") or 0.0)
                retry_attempt = max(0, int(candidate.get("retry_attempt") or 0))
                created_at = float(candidate.get("created_at") or now)
                finished_at = float(candidate.get("finished_at") or 0.0)
            except (TypeError, ValueError):
                continue
            if not send_id or operation not in {"once", "reply"}:
                continue
            last_error = str(candidate.get("last_error") or "")
            status = str(candidate.get("status") or "").strip()
            if not status:
                status = "rate_limited" if retry_at > 0 or retry_attempt > 0 else "queued"
            if status == "running":
                status = "dead_lettered"
                last_error = (
                    last_error
                    or "Delivery state unknown after Prompta restarted during an in-flight send"
                )
            if status == "dead_lettered" and _is_legacy_pre_send_outage(last_error):
                logger.info(
                    "Requeueing legacy Prompta UI send blocked before delivery send_id=%s",
                    send_id,
                )
                status = "queued"
                retry_at = 0.0
                retry_attempt = 0
                last_error = ""
                finished_at = 0.0
            if status in {"cancelled", "dead_lettered", "succeeded"}:
                record = {
                    "send_id": send_id,
                    "operation": operation,
                    "message": message,
                    "conversation_id": conversation_id,
                    "attachments": attachments,
                    "client_id": client_id,
                    "status": status,
                    "retry_at": 0.0,
                    "retry_attempt": retry_attempt,
                    "created_at": created_at,
                }
                if last_error:
                    record["last_error"] = last_error
                if finished_at > 0:
                    record["finished_at"] = finished_at
                self._recoverable[send_id] = record
                self._jobs[send_id] = {
                    "send_id": send_id,
                    "operation": operation,
                    "message": message,
                    "client_id": client_id,
                    "status": status,
                    "conversation_id": conversation_id,
                    "error": last_error if status == "dead_lettered" else "",
                    "created_at": created_at,
                    "updated_at": finished_at or created_at,
                    "attachment_count": len(attachments),
                    "retry_at": 0.0,
                    "retry_after_seconds": 0,
                    "retry_attempt": retry_attempt,
                    "attachment_names": [Path(value).name for value in attachments],
                    "_attachments": attachments,
                }
                if client_id:
                    self._client_jobs[client_id] = send_id
                self._upsert_database_record(record)
                continue
            if status not in {"queued", "rate_limited", "retrying"}:
                status = "queued"
            restored_status = status if status in {"rate_limited", "retrying"} else "queued"
            record = {
                "send_id": send_id,
                "operation": operation,
                "message": message,
                "conversation_id": conversation_id,
                "attachments": attachments,
                "client_id": client_id,
                "status": restored_status,
                "retry_at": retry_at,
                "retry_attempt": retry_attempt,
                "created_at": created_at,
            }
            if last_error:
                record["last_error"] = last_error
            self._recoverable[send_id] = record
            remaining = (
                max(0.0, retry_at - now) if restored_status in {"rate_limited", "retrying"} else 0.0
            )
            self._jobs[send_id] = {
                "send_id": send_id,
                "operation": operation,
                "message": message,
                "client_id": client_id,
                "status": restored_status,
                "conversation_id": conversation_id,
                "error": (
                    "ChatGPT rate limited this account"
                    if restored_status == "rate_limited"
                    else last_error
                    if restored_status == "retrying"
                    else ""
                ),
                "created_at": created_at,
                "updated_at": now,
                "attachment_count": len(attachments),
                "retry_at": retry_at if restored_status in {"rate_limited", "retrying"} else 0.0,
                "retry_after_seconds": max(0, math.ceil(remaining)),
                "retry_attempt": retry_attempt
                if restored_status in {"rate_limited", "retrying"}
                else 0,
                "attachment_names": [Path(value).name for value in attachments],
                "_attachments": attachments,
            }
            if client_id:
                self._client_jobs[client_id] = send_id
            self._upsert_database_record(record)
            if restored_status == "rate_limited":
                max_retry_at = max(max_retry_at, retry_at)
                max_attempt = max(max_attempt, retry_attempt)
            restored.append(record)

        # Recovery preserves FIFO ordering. Only the queue head owns retry
        # timing; later jobs wait as plain queued work until it completes.
        if restored:
            for record in restored[1:]:
                if record["status"] not in {"queued", "rate_limited", "retrying"}:
                    continue
                record["status"] = "queued"
                record["retry_at"] = 0.0
                job = self._jobs.get(record["send_id"])
                if job is not None:
                    job.update(
                        status="queued",
                        retry_at=0.0,
                        retry_after_seconds=0,
                    )
                self._upsert_database_record(record)

        if self._recoverable:
            with self._recovery_lock:
                self._write_recovery_locked()
        if max_attempt:
            with self._rate_limit_lock:
                self._rate_limit_backoff.restore(
                    {
                        "attempts": max_attempt,
                        "blocked_until_epoch": max_retry_at,
                        "last_limited_at_epoch": now,
                    }
                )
        if self._jobs:
            self._revision += 1
        if restored:
            logger.info("Restoring %d durable Prompta UI send(s)", len(restored))
            self._work_event.set()
        elif path is not None and not self._recoverable:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning(
                    "Could not clear invalid Prompta UI retry state %s", path, exc_info=True
                )

    @staticmethod
    def _as_rate_limit_error(exc: Exception) -> RateLimitError | None:
        if isinstance(exc, RateLimitError):
            return exc
        message = str(exc)
        if is_rate_limited_text(message):
            return RateLimitError(message, retry_after=parse_retry_after(message))
        return None

    def _rate_limit_remaining(self) -> tuple[float, int]:
        with self._rate_limit_lock:
            return self._rate_limit_backoff.remaining(), self._rate_limit_backoff.attempts

    def _record_rate_limit(self, exc: RateLimitError) -> tuple[float, int]:
        with self._rate_limit_lock:
            remaining = self._rate_limit_backoff.remaining()
            if remaining > 0:
                return remaining, max(1, self._rate_limit_backoff.attempts)
            delay = self._rate_limit_backoff.record(exc.retry_after)
            return delay, self._rate_limit_backoff.attempts

    def _reset_rate_limit_backoff(self) -> None:
        with self._rate_limit_lock:
            self._rate_limit_backoff.reset()

    def _job_with_queue_position_locked(self, job: dict[str, Any]) -> dict[str, Any]:
        result = dict(job)
        result.pop("_attachments", None)
        if str(job.get("status") or "") != "queued":
            return result

        send_id = str(job.get("send_id") or "")
        position = 0
        for candidate in self._jobs.values():
            if str(candidate.get("status") or "") in {"queued", "retrying", "rate_limited"}:
                position += 1
            if str(candidate.get("send_id") or "") == send_id:
                break
        if position > 0:
            result["queue_position"] = position

            now = time.time()
            slot_backoff = float(DEFAULT_RETRY_AFTER)
            head_remaining = 0.0
            active_rate_limit = False
            for candidate in self._jobs.values():
                if str(candidate.get("status") or "") != "rate_limited":
                    continue
                retry_at = float(candidate.get("retry_at") or 0.0)
                remaining = max(0.0, retry_at - now)
                if remaining <= 0:
                    continue
                observed_backoff = float(candidate.get("retry_after_seconds") or 0.0)
                slot_backoff = max(slot_backoff, observed_backoff)
                head_remaining = remaining
                active_rate_limit = True
                break

            slots_after_head = max(0, position - 1) if active_rate_limit else position
            queue_eta_seconds = head_remaining + slots_after_head * slot_backoff
            result["queue_eta_seconds"] = max(1, math.ceil(queue_eta_seconds))
            result["queue_eta_at"] = now + queue_eta_seconds
        return result

    def _coalesce_queued_reply_locked(
        self,
        *,
        message: str,
        conversation_id: str,
        attachments: list[str],
        client_id: str,
        now: float,
    ) -> dict[str, Any] | None:
        if not conversation_id:
            return None

        for existing in self._jobs.values():
            if (
                str(existing.get("operation") or "") != "reply"
                or str(existing.get("conversation_id") or "") != conversation_id
                or str(existing.get("status") or "") != "queued"
            ):
                continue

            send_id = str(existing.get("send_id") or "")
            primary_client_id = str(existing.get("client_id") or "")
            existing_message = str(existing.get("message") or "")
            merged_message = "\n".join(value for value in (existing_message, message) if value)
            raw_existing_attachments = existing.get("_attachments", [])
            existing_attachments = (
                [str(value) for value in raw_existing_attachments if isinstance(value, str)]
                if isinstance(raw_existing_attachments, list)
                else []
            )
            merged_attachments = [*existing_attachments, *attachments]

            existing.update(
                message=merged_message,
                updated_at=now,
                attachment_count=len(merged_attachments),
                attachment_names=[Path(value).name for value in merged_attachments],
                _attachments=merged_attachments,
            )
            if client_id:
                self._client_jobs[client_id] = send_id

            if self._queue_path is None:
                for index, task in enumerate(self._fallback_tasks):
                    if task[0] != send_id:
                        continue
                    self._fallback_tasks[index] = (
                        send_id,
                        "reply",
                        merged_message,
                        conversation_id,
                        merged_attachments,
                        primary_client_id,
                    )
                    break
            elif self._recovery_path is None:
                self._upsert_database_record(
                    {
                        "send_id": send_id,
                        "operation": "reply",
                        "message": merged_message,
                        "conversation_id": conversation_id,
                        "attachments": merged_attachments,
                        "client_id": primary_client_id,
                        "status": "queued",
                        "created_at": float(existing.get("created_at") or now),
                    }
                )
            else:
                self._remember_recoverable(
                    send_id=send_id,
                    operation="reply",
                    message=merged_message,
                    conversation_id=conversation_id,
                    attachments=merged_attachments,
                    client_id=primary_client_id,
                    created_at=float(existing.get("created_at") or now),
                    status="queued",
                )

            self._revision += 1
            self._work_event.set()
            return self._job_with_queue_position_locked(existing)

        return None

    def submit(
        self,
        *,
        operation: str,
        message: str,
        conversation_id: str = "",
        attachments: list[str] | None = None,
        client_id: str = "",
    ) -> dict[str, Any]:
        now = time.time()
        normalized_client_id = client_id.strip()
        attachment_paths = list(attachments or [])
        send_id = uuid.uuid4().hex
        job = {
            "send_id": send_id,
            "operation": operation,
            "message": message,
            "client_id": normalized_client_id,
            "status": "queued",
            "conversation_id": conversation_id,
            "error": "",
            "created_at": now,
            "updated_at": now,
            "attachment_count": len(attachment_paths),
            "attachment_names": [Path(value).name for value in attachment_paths],
            "_attachments": attachment_paths,
        }
        with self._lock:
            cutoff = now - 3600.0
            with self._recovery_lock:
                durable_terminal_send_ids = {
                    key
                    for key, value in self._recoverable.items()
                    if value.get("status") in {"cancelled", "succeeded", "dead_lettered"}
                }
            self._jobs = {
                key: value
                for key, value in self._jobs.items()
                if float(value.get("updated_at") or 0.0) >= cutoff
                or key in durable_terminal_send_ids
            }
            live_send_ids = set(self._jobs)
            self._client_jobs = {
                key: value for key, value in self._client_jobs.items() if value in live_send_ids
            }
            if normalized_client_id:
                existing_send_id = self._client_jobs.get(normalized_client_id)
                existing = self._jobs.get(existing_send_id or "")
                if existing is not None:
                    self._cleanup_attachments(attachment_paths)
                    if (
                        self._on_success is not None
                        and str(existing.get("status") or "") == "succeeded"
                        and str(existing.get("conversation_id") or "")
                    ):
                        try:
                            self._on_success(
                                normalized_client_id,
                                str(existing["conversation_id"]),
                                message,
                            )
                        except Exception:
                            logger.warning(
                                "Could not bind idempotent Prompta image preview send_id=%s",
                                existing_send_id,
                                exc_info=True,
                            )
                    return self._job_with_queue_position_locked(existing)

            if operation == "reply":
                coalesced = self._coalesce_queued_reply_locked(
                    message=message,
                    conversation_id=conversation_id,
                    attachments=attachment_paths,
                    client_id=normalized_client_id,
                    now=now,
                )
                if coalesced is not None:
                    return coalesced

            try:
                self._remember_recoverable(
                    send_id=send_id,
                    operation=operation,
                    message=message,
                    conversation_id=conversation_id,
                    attachments=attachment_paths,
                    client_id=normalized_client_id,
                    created_at=now,
                    status="queued",
                )
            except Exception:
                self._cleanup_attachments(attachment_paths)
                raise
            self._jobs[send_id] = job
            if normalized_client_id:
                self._client_jobs[normalized_client_id] = send_id
            self._revision += 1
            if self._queue_path is None:
                self._fallback_tasks.append(
                    (
                        send_id,
                        operation,
                        message,
                        conversation_id,
                        attachment_paths,
                        normalized_client_id,
                    )
                )
            result = self._job_with_queue_position_locked(job)
            self._work_event.set()
        return result

    def get(self, send_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(send_id)
            return self._job_with_queue_position_locked(job) if job is not None else None

    def cancel(self, send_id: str) -> bool:
        """Cancel a pending send and remove its durable queue record."""
        attachments: list[str] = []
        with self._lock:
            job = self._jobs.get(send_id)
            if job is None or str(job.get("status") or "") not in {
                "queued",
                "running",
                "retrying",
                "rate_limited",
                "failed",
                "dead_lettered",
            }:
                return False
            status = str(job.get("status") or "")
            with self._recovery_lock:
                recoverable = self._recoverable.get(send_id) or {}
            attachments = [
                value for value in recoverable.get("attachments", []) if isinstance(value, str)
            ]
            if status == "running":
                # The browser sender cannot be interrupted safely, but prevent
                # the result from being surfaced or retried after it returns.
                self._cancelled.add(send_id)
                job["status"] = "cancelled"
                self._revision += 1
                self._remember_recoverable(
                    send_id=send_id,
                    operation=str(job.get("operation") or ""),
                    message=str(job.get("message") or ""),
                    conversation_id=str(job.get("conversation_id") or ""),
                    attachments=attachments,
                    client_id=str(job.get("client_id") or ""),
                    created_at=float(job.get("created_at") or time.time()),
                    status="cancelled",
                    finished_at=time.time(),
                )
                return True
            self._jobs.pop(send_id, None)
            client_id = str(job.get("client_id") or "")
            if client_id and self._client_jobs.get(client_id) == send_id:
                self._client_jobs.pop(client_id, None)
            self._fallback_tasks = [task for task in self._fallback_tasks if task[0] != send_id]
            self._revision += 1
        self._forget_recoverable(send_id)
        self._cleanup_attachments(attachments)
        self._work_event.set()
        return True

    def bump_to_front(self, send_id: str) -> dict[str, Any] | None:
        """Move a pending send ahead of the other queued sends."""
        with self._lock:
            job = self._jobs.get(send_id)
            if job is None or str(job.get("status") or "") not in {
                "queued",
                "retrying",
                "rate_limited",
            }:
                return None

            if self._queue_path is None:
                for index, task in enumerate(self._fallback_tasks):
                    if task[0] != send_id:
                        continue
                    self._fallback_tasks.insert(0, self._fallback_tasks.pop(index))
                    break
            else:
                self._bump_database_record(send_id)

            reordered: dict[str, dict[str, Any]] = {}
            inserted = False
            for key, candidate in self._jobs.items():
                if key == send_id:
                    continue
                if not inserted and str(candidate.get("status") or "") in {
                    "queued",
                    "retrying",
                    "rate_limited",
                }:
                    reordered[send_id] = job
                    inserted = True
                reordered[key] = candidate
            if not inserted:
                reordered[send_id] = job
            self._jobs = reordered
            self._revision += 1
            result = self._job_with_queue_position_locked(job)
            self._work_event.set()
            return result

    def list_pending(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                self._job_with_queue_position_locked(job)
                for job in self._jobs.values()
                if str(job.get("status") or "") in {"queued", "running", "retrying", "rate_limited"}
            ]

    def list_conversation_receipts(
        self,
        *,
        succeeded_within_seconds: float = 3600.0,
    ) -> list[dict[str, Any]]:
        now = time.time()
        with self._lock:
            result = []
            for job in self._jobs.values():
                status = str(job.get("status") or "")
                if str(job.get("operation") or "") != "once":
                    continue
                conversation_id = str(job.get("conversation_id") or "")
                if status == "succeeded":
                    if not conversation_id:
                        continue
                    updated_at = float(job.get("updated_at") or job.get("created_at") or 0.0)
                    if (
                        succeeded_within_seconds >= 0
                        and now - updated_at > succeeded_within_seconds
                    ):
                        continue
                elif status not in {"queued", "running", "retrying", "rate_limited"}:
                    continue
                result.append(self._job_with_queue_position_locked(job))
            return result

    @property
    def revision(self) -> int:
        with self._lock:
            return self._revision

    def _update(self, send_id: str, **updates: Any) -> None:
        with self._lock:
            job = self._jobs.get(send_id)
            if job is None:
                return
            job.update(updates)
            job["updated_at"] = time.time()
            database_updates = {
                key: updates[key]
                for key in (
                    "status",
                    "error",
                    "conversation_id",
                    "retry_at",
                    "retry_attempt",
                )
                if key in updates
            }
            if database_updates:
                connection = self._connect_database()
                if connection is not None:
                    try:
                        assignments = ", ".join(f"{key} = ?" for key in database_updates)
                        values = list(database_updates.values())
                        values.extend([time.time(), send_id])
                        connection.execute(
                            f"UPDATE send_jobs SET {assignments}, updated_at = ? WHERE send_id = ?",
                            values,
                        )
                        connection.commit()
                    finally:
                        connection.close()
            self._revision += 1

    def _run(
        self,
        send_id: str,
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str],
        client_id: str = "",
    ) -> None:
        try:
            with self._lock:
                cancelled = send_id in self._cancelled
            if cancelled:
                self._cancelled.discard(send_id)
                self._forget_recoverable(send_id)
                self._jobs.pop(send_id, None)
                return
            current = self.get(send_id) or {}
            durable_queue = self._queue_path is not None
            generic_attempt = (
                max(0, int(current.get("retry_attempt") or 0))
                if str(current.get("status") or "") == "retrying"
                else 0
            )
            infrastructure_attempt = 0
            local_retry_at = float(current.get("retry_at") or 0.0)
            if str(current.get("status") or "") == "retrying" and local_retry_at > time.time():
                if durable_queue:
                    return
                self._sleep(local_retry_at - time.time())
            while True:
                remaining, attempt = self._rate_limit_remaining()
                if remaining > 0:
                    retry_at = time.time() + remaining
                    self._update(
                        send_id,
                        status="rate_limited",
                        error="ChatGPT rate limited this account",
                        retry_at=retry_at,
                        retry_after_seconds=max(1, math.ceil(remaining)),
                        retry_attempt=max(1, attempt),
                    )
                    current = self.get(send_id) or {}
                    self._remember_recoverable(
                        send_id=send_id,
                        operation=operation,
                        message=message,
                        conversation_id=conversation_id,
                        attachments=attachments,
                        client_id=client_id,
                        created_at=float(current.get("created_at") or time.time()),
                        status="rate_limited",
                        retry_at=retry_at,
                        retry_attempt=max(1, attempt),
                    )
                    self._sleep(remaining)

                self._update(
                    send_id,
                    status="running",
                    error="",
                    retry_at=0.0,
                    retry_after_seconds=0,
                )
                with self._lock:
                    cancelled = send_id in self._cancelled
                if cancelled:
                    self._cancelled.discard(send_id)
                    self._forget_recoverable(send_id)
                    self._jobs.pop(send_id, None)
                    return
                current = self.get(send_id) or {}
                self._remember_recoverable(
                    send_id=send_id,
                    operation=operation,
                    message=message,
                    conversation_id=conversation_id,
                    attachments=attachments,
                    client_id=client_id,
                    created_at=float(current.get("created_at") or time.time()),
                    status="running",
                    retry_attempt=generic_attempt,
                )
                with self._lock:
                    latest = self._jobs.get(send_id)
                    if latest is not None:
                        message = str(latest.get("message") or message)
                        raw_latest_attachments = latest.get("_attachments")
                        if isinstance(raw_latest_attachments, list):
                            attachments = [
                                str(value)
                                for value in raw_latest_attachments
                                if isinstance(value, str)
                            ]

                try:
                    result = self._sender(operation, message, conversation_id, attachments)
                except Exception as exc:
                    if isinstance(exc, ControlDeferredError):
                        current = self.get(send_id) or {}
                        delay = exc.retry_after
                        retry_at = time.time() + delay
                        logger.info(
                            "Prompta UI send deferred send_id=%s operation=%s conversation=%s "
                            "retrying_in=%.1fs: %s",
                            send_id,
                            operation,
                            conversation_id or "new",
                            delay,
                            exc,
                        )
                        self._update(
                            send_id,
                            status="retrying",
                            error=str(exc),
                            retry_at=retry_at,
                            retry_after_seconds=max(1, math.ceil(delay)),
                            retry_attempt=generic_attempt,
                        )
                        self._remember_recoverable(
                            send_id=send_id,
                            operation=operation,
                            message=message,
                            conversation_id=conversation_id,
                            attachments=attachments,
                            client_id=client_id,
                            created_at=float(current.get("created_at") or time.time()),
                            status="retrying",
                            retry_at=retry_at,
                            retry_attempt=generic_attempt,
                            last_error=str(exc),
                        )
                        if durable_queue:
                            return
                        self._sleep(delay)
                        continue

                    if isinstance(exc, ControlUnavailableError):
                        infrastructure_attempt += 1
                        current = self.get(send_id) or {}
                        delay = min(
                            _SEND_RETRY_CAP_SECONDS,
                            _SEND_RETRY_BASE_SECONDS * (2 ** min(infrastructure_attempt - 1, 10)),
                        )
                        retry_at = time.time() + delay
                        logger.warning(
                            "Prompta UI backend unavailable send_id=%s operation=%s "
                            "conversation=%s retry=%d backing_off=%.1fs: %s",
                            send_id,
                            operation,
                            conversation_id or "new",
                            infrastructure_attempt,
                            delay,
                            exc,
                        )
                        self._update(
                            send_id,
                            status="retrying",
                            error=str(exc),
                            retry_at=retry_at,
                            retry_after_seconds=max(1, math.ceil(delay)),
                            retry_attempt=generic_attempt,
                        )
                        self._remember_recoverable(
                            send_id=send_id,
                            operation=operation,
                            message=message,
                            conversation_id=conversation_id,
                            attachments=attachments,
                            client_id=client_id,
                            created_at=float(current.get("created_at") or time.time()),
                            status="retrying",
                            retry_at=retry_at,
                            retry_attempt=generic_attempt,
                            last_error=str(exc),
                        )
                        if durable_queue:
                            return
                        self._sleep(delay)
                        continue

                    rate_limit = self._as_rate_limit_error(exc)
                    if rate_limit is None:
                        generic_attempt += 1
                        current = self.get(send_id) or {}
                        if generic_attempt < _SEND_RETRY_MAX_ATTEMPTS:
                            delay = min(
                                _SEND_RETRY_CAP_SECONDS,
                                _SEND_RETRY_BASE_SECONDS * (2 ** (generic_attempt - 1)),
                            )
                            retry_at = time.time() + delay
                            logger.warning(
                                "Prompta UI send failed send_id=%s operation=%s conversation=%s "
                                "attempt=%d/%d backing_off=%.1fs: %s",
                                send_id,
                                operation,
                                conversation_id or "new",
                                generic_attempt,
                                _SEND_RETRY_MAX_ATTEMPTS,
                                delay,
                                exc,
                            )
                            self._update(
                                send_id,
                                status="retrying",
                                error=str(exc),
                                retry_at=retry_at,
                                retry_after_seconds=max(1, math.ceil(delay)),
                                retry_attempt=generic_attempt,
                            )
                            self._remember_recoverable(
                                send_id=send_id,
                                operation=operation,
                                message=message,
                                conversation_id=conversation_id,
                                attachments=attachments,
                                client_id=client_id,
                                created_at=float(current.get("created_at") or time.time()),
                                status="retrying",
                                retry_at=retry_at,
                                retry_attempt=generic_attempt,
                                last_error=str(exc),
                            )
                            self._sleep(delay)
                            continue

                        logger.exception(
                            "Prompta UI send moved to dead letter queue send_id=%s operation=%s conversation=%s attempts=%d",
                            send_id,
                            operation,
                            conversation_id or "new",
                            generic_attempt,
                        )
                        self._remember_recoverable(
                            send_id=send_id,
                            operation=operation,
                            message=message,
                            conversation_id=conversation_id,
                            attachments=attachments,
                            client_id=client_id,
                            created_at=float(current.get("created_at") or time.time()),
                            status="dead_lettered",
                            retry_attempt=generic_attempt,
                            last_error=str(exc),
                        )
                        self._update(
                            send_id,
                            status="dead_lettered",
                            error=str(exc),
                            retry_at=0.0,
                            retry_after_seconds=0,
                            retry_attempt=generic_attempt,
                        )
                        return

                    delay, attempt = self._record_rate_limit(rate_limit)
                    retry_at = time.time() + delay
                    logger.warning(
                        "Prompta UI send rate limited send_id=%s operation=%s conversation=%s "
                        "attempt=%d retry_after=%ds backing_off=%.1fs",
                        send_id,
                        operation,
                        conversation_id or "new",
                        attempt,
                        rate_limit.retry_after,
                        delay,
                    )
                    self._update(
                        send_id,
                        status="rate_limited",
                        error=str(rate_limit),
                        retry_at=retry_at,
                        retry_after_seconds=max(1, math.ceil(delay)),
                        retry_attempt=attempt,
                    )
                    current = self.get(send_id) or {}
                    self._remember_recoverable(
                        send_id=send_id,
                        operation=operation,
                        message=message,
                        conversation_id=conversation_id,
                        attachments=attachments,
                        client_id=client_id,
                        created_at=float(current.get("created_at") or time.time()),
                        status="rate_limited",
                        retry_at=retry_at,
                        retry_attempt=attempt,
                    )
                    self._sleep(delay)
                    continue

                self._reset_rate_limit_backoff()
                with self._lock:
                    cancelled = send_id in self._cancelled
                if cancelled:
                    self._cancelled.discard(send_id)
                    self._forget_recoverable(send_id)
                    self._delete_database_record(send_id)
                    self._jobs.pop(send_id, None)
                    return
                current = self.get(send_id) or {}
                if client_id:
                    self._remember_recoverable(
                        send_id=send_id,
                        operation=operation,
                        message=message,
                        conversation_id=result,
                        attachments=[],
                        client_id=client_id,
                        created_at=float(current.get("created_at") or time.time()),
                        status="succeeded",
                        finished_at=time.time(),
                    )
                else:
                    self._forget_recoverable(send_id)
                self._update(
                    send_id,
                    status="succeeded",
                    conversation_id=result,
                    error="",
                    retry_at=0.0,
                    retry_after_seconds=0,
                )
                if self._on_success is not None and client_id:
                    try:
                        self._on_success(client_id, result, message)
                    except Exception:
                        logger.warning(
                            "Could not bind Prompta image preview send_id=%s conversation=%s",
                            send_id,
                            result,
                            exc_info=True,
                        )
                return
        finally:
            current = self.get(send_id) or {}
            if str(current.get("status") or "") not in {
                "queued",
                "running",
                "retrying",
                "rate_limited",
                "dead_lettered",
            }:
                self._cleanup_attachments(attachments)
