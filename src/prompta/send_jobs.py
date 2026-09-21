from __future__ import annotations

import json
import logging
import math
import os
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .rate_limit import (
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
        on_success: Callable[[str, str, str], None] | None = None,
    ) -> None:
        self._sender = sender
        self._sleep = sleeper
        self._on_success = on_success
        self._jobs: dict[str, dict[str, Any]] = {}
        self._client_jobs: dict[str, str] = {}
        self._lock = threading.Lock()
        self._rate_limit_lock = threading.Lock()
        self._rate_limit_backoff = RateLimitBackoff()
        self._revision = 0
        self._recovery_path = recovery_path
        self._recovery_lock = threading.Lock()
        self._recoverable: dict[str, dict[str, Any]] = {}
        self._restore_recoverable()

    def _write_recovery_locked(self) -> None:
        if self._recovery_path is None:
            return
        path = self._recovery_path
        if not self._recoverable:
            path.unlink(missing_ok=True)
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(f"{path.suffix}.tmp")
        payload = json.dumps({"jobs": list(self._recoverable.values())}, ensure_ascii=False)
        with temporary.open("w", encoding="utf-8") as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        temporary.replace(path)

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
        if self._recovery_path is None:
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
        expired_attachments: list[str] = []
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
                    raw_attachments = expired_record.get("attachments", [])
                    if isinstance(raw_attachments, list):
                        expired_attachments.extend(
                            value for value in raw_attachments if isinstance(value, str)
                        )
            if status in {"dead_lettered", "succeeded"}:
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
        if expired_attachments:
            self._cleanup_attachments(
                [
                    attachment
                    for attachment in expired_attachments
                    if attachment not in retained_attachments
                ]
            )

    def _forget_recoverable(self, send_id: str) -> None:
        if self._recovery_path is None:
            return
        with self._recovery_lock:
            if self._recoverable.pop(send_id, None) is not None:
                self._write_recovery_locked()

    def _restore_recoverable(self) -> None:
        path = self._recovery_path
        if path is None or not path.exists():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            records = payload.get("jobs", []) if isinstance(payload, dict) else []
            records = records if isinstance(records, list) else []
        except (OSError, ValueError):
            logger.warning("Could not restore Prompta UI retry state %s", path, exc_info=True)
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
                last_error = last_error or "Delivery state unknown after Prompta restarted during an in-flight send"
            if status in {"dead_lettered", "succeeded"}:
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
                    "status": status,
                    "conversation_id": conversation_id,
                    "error": last_error if status == "dead_lettered" else "",
                    "created_at": created_at,
                    "updated_at": finished_at or created_at,
                    "attachment_count": len(attachments),
                    "retry_at": 0.0,
                    "retry_after_seconds": 0,
                    "retry_attempt": retry_attempt,
                }
                if client_id:
                    self._client_jobs[client_id] = send_id
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
            remaining = max(0.0, retry_at - now) if restored_status in {"rate_limited", "retrying"} else 0.0
            self._jobs[send_id] = {
                "send_id": send_id,
                "operation": operation,
                "status": restored_status,
                "conversation_id": conversation_id,
                "error": (
                    "ChatGPT rate limited this account"
                    if restored_status == "rate_limited"
                    else last_error if restored_status == "retrying" else ""
                ),
                "created_at": created_at,
                "updated_at": now,
                "attachment_count": len(attachments),
                "retry_at": retry_at if restored_status in {"rate_limited", "retrying"} else 0.0,
                "retry_after_seconds": max(0, math.ceil(remaining)),
                "retry_attempt": retry_attempt if restored_status in {"rate_limited", "retrying"} else 0,
            }
            if client_id:
                self._client_jobs[client_id] = send_id
            if restored_status == "rate_limited":
                max_retry_at = max(max_retry_at, retry_at)
                max_attempt = max(max_attempt, retry_attempt)
            restored.append(record)

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
            for record in restored:
                threading.Thread(
                    target=self._run,
                    args=(
                        record["send_id"],
                        record["operation"],
                        record["message"],
                        record["conversation_id"],
                        list(record["attachments"]),
                        record["client_id"],
                    ),
                    name=f"prompta-ui-send-{record['send_id'][:8]}",
                    daemon=True,
                ).start()
        elif not self._recoverable:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning("Could not clear invalid Prompta UI retry state %s", path, exc_info=True)

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
            "status": "queued",
            "conversation_id": conversation_id,
            "error": "",
            "created_at": now,
            "updated_at": now,
            "attachment_count": len(attachment_paths),
        }
        with self._lock:
            cutoff = now - 3600.0
            with self._recovery_lock:
                durable_terminal_send_ids = {
                    key
                    for key, value in self._recoverable.items()
                    if value.get("status") in {"succeeded", "dead_lettered"}
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
                    return dict(existing)
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
        threading.Thread(
            target=self._run,
            args=(
                send_id,
                operation,
                message,
                conversation_id,
                attachment_paths,
                normalized_client_id,
            ),
            name=f"prompta-ui-send-{send_id[:8]}",
            daemon=True,
        ).start()
        return dict(job)

    def get(self, send_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(send_id)
            return dict(job) if job is not None else None

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
            current = self.get(send_id) or {}
            generic_attempt = (
                max(0, int(current.get("retry_attempt") or 0))
                if str(current.get("status") or "") == "retrying"
                else 0
            )
            local_retry_at = float(current.get("retry_at") or 0.0)
            if str(current.get("status") or "") == "retrying" and local_retry_at > time.time():
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
                try:
                    result = self._sender(operation, message, conversation_id, attachments)
                except Exception as exc:
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
            if current.get("status") != "dead_lettered":
                self._cleanup_attachments(attachments)
