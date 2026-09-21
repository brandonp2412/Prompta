"""Local web UI for Prompta's cached conversations and live replies."""

from __future__ import annotations

import argparse
import asyncio
import base64
import binascii
import hashlib
import json
import logging
import math
import mimetypes
import re
import sqlite3
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlparse

from .cache import DEFAULT_CACHE_PATH, ChatCache
from .core import (
    DEFAULT_JOBS_PATH,
    DEFAULT_STATE_PATH,
    RateLimitBackoff,
    RateLimitError,
    _daemon_is_running,
    _send_once_via_control,
    _send_reply_via_control,
    add_job,
    is_rate_limited_text,
    parse_retry_after,
)

logger = logging.getLogger(__name__)
_STATIC_ROOT = Path(__file__).with_name("static")
_DAEMON_STARTUP_CHECKS = 10
_DAEMON_STARTUP_POLL_SECONDS = 0.1
_DAEMON_RESTART_GRACE_CHECKS = 120


def _git_short_head() -> str:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "--short=8", "HEAD"],
            cwd=Path(__file__).resolve().parents[2],
            check=False,
            capture_output=True,
            text=True,
            timeout=1,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return completed.stdout.strip() if completed.returncode == 0 else ""


_UI_HEAD = _git_short_head()


class ReadOnlyChatStore:
    """Open fresh read-only data sources for each web request."""

    def __init__(
        self,
        path: Path = DEFAULT_CACHE_PATH,
        log_path: Path | None = None,
        journal_unit: str = "prompta.service",
    ) -> None:
        self.path = path.expanduser()
        self.log_path = (
            log_path.expanduser()
            if log_path is not None
            else self.path.with_name("prompta-nox.log")
        )
        self.journal_unit = journal_unit.strip()

    def _connect(self) -> sqlite3.Connection:
        if not self.path.is_file():
            raise FileNotFoundError(self.path)
        connection = sqlite3.connect(
            f"{self.path.resolve().as_uri()}?mode=ro",
            uri=True,
            timeout=2.0,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA query_only=ON")
        connection.execute("PRAGMA busy_timeout=2000")
        return connection

    def conversations(self, *, limit: int = 200, query: str = "") -> list[dict[str, Any]]:
        search = query.strip()
        where = ""
        parameters: list[Any] = []
        if search:
            where = """
                WHERE c.title COLLATE NOCASE LIKE ? ESCAPE '!'
                   OR c.job_name COLLATE NOCASE LIKE ? ESCAPE '!'
                   OR c.prompt COLLATE NOCASE LIKE ? ESCAPE '!'
                   OR EXISTS (
                        SELECT 1 FROM messages sm
                        WHERE sm.conversation_id = c.id
                          AND sm.message_key NOT LIKE 'request-placeholder-%'
                          AND sm.content COLLATE NOCASE LIKE ? ESCAPE '!'
                    )
            """
            escaped = search.replace("!", "!!").replace("%", "!%").replace("_", "!_")
            needle = f"%{escaped}%"
            parameters.extend([needle, needle, needle, needle])
        parameters.append(max(1, min(limit, 500)))
        try:
            with self._connect() as connection:
                rows = connection.execute(
                    f"""
                    SELECT
                        c.id,
                        c.job_name,
                        c.prompt,
                        c.url,
                        c.title,
                        c.status,
                        c.created_at,
                        c.updated_at,
                        c.completed_at,
                        COALESCE(
                            (
                                SELECT MAX(m.created_at) FROM messages m
                                WHERE m.conversation_id = c.id
                                  AND m.message_key NOT LIKE 'request-placeholder-%'
                            ),
                            c.created_at
                        ) AS last_message_at,
                        COALESCE(
                            (
                                SELECT m.content FROM messages m
                                WHERE m.conversation_id = c.id
                                  AND m.message_key NOT LIKE 'request-placeholder-%'
                                ORDER BY m.ordinal DESC LIMIT 1
                            ),
                            NULLIF(c.prompt, '')
                        ) AS preview,
                        CASE
                            WHEN EXISTS (
                                SELECT 1 FROM messages m
                                WHERE m.conversation_id = c.id
                                  AND m.message_key NOT LIKE 'request-placeholder-%'
                            )
                            THEN (
                                SELECT COUNT(*) FROM messages m
                                WHERE m.conversation_id = c.id
                                  AND m.message_key NOT LIKE 'request-placeholder-%'
                            )
                            WHEN TRIM(c.prompt) <> '' THEN 1
                            ELSE 0
                        END AS message_count
                    FROM conversations c
                    {where}
                    ORDER BY
                        CASE c.status WHEN 'active' THEN 0 ELSE 1 END,
                        c.updated_at DESC
                    LIMIT ?
                    """,
                    parameters,
                ).fetchall()
        except (FileNotFoundError, sqlite3.DatabaseError):
            return []
        return [dict(row) for row in rows]

    def conversation(self, conversation_id: str) -> dict[str, Any] | None:
        try:
            with self._connect() as connection:
                conversation = connection.execute(
                    """
                    SELECT id, job_name, prompt, url, title, status,
                           created_at, updated_at, completed_at
                    FROM conversations
                    WHERE id = ?
                    """,
                    (conversation_id,),
                ).fetchone()
                if conversation is None:
                    return None
                messages = connection.execute(
                    """
                    SELECT message_key, ordinal, role, content, status,
                           created_at, updated_at
                    FROM messages
                    WHERE conversation_id = ?
                      AND message_key NOT LIKE 'request-placeholder-%'
                    ORDER BY ordinal
                    """,
                    (conversation_id,),
                ).fetchall()
        except (FileNotFoundError, sqlite3.DatabaseError):
            return None
        payload = dict(conversation)
        message_payloads = [dict(message) for message in messages]
        if payload.get("status") != "active":
            for message in message_payloads:
                message["status"] = "complete"
        prompt = str(payload.get("prompt") or "")
        if not message_payloads and prompt.strip():
            message_payloads = [
                {
                    "message_key": "__prompta_prompt__",
                    "ordinal": 0,
                    "role": "user",
                    "content": prompt,
                    "status": "complete",
                    "created_at": payload["created_at"],
                    "updated_at": payload["updated_at"],
                }
            ]
        payload["messages"] = message_payloads
        return payload

    def logs(self, *, limit: int = 500) -> dict[str, Any]:
        bounded_limit = max(1, min(limit, 2000))
        if self.log_path.is_file():
            try:
                text = self.log_path.read_text(errors="replace")
                updated_at = self.log_path.stat().st_mtime
            except OSError:
                pass
            else:
                return {
                    "exists": True,
                    "lines": text.splitlines()[-bounded_limit:],
                    "updated_at": updated_at,
                    "source": "file",
                }

        if not self.journal_unit:
            return {
                "exists": False,
                "lines": [],
                "updated_at": None,
                "source": "none",
            }

        try:
            completed = subprocess.run(
                [
                    "journalctl",
                    "--user",
                    "-u",
                    self.journal_unit,
                    "-n",
                    str(bounded_limit),
                    "--no-pager",
                    "--output=short-iso",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=2.0,
            )
        except (OSError, subprocess.SubprocessError):
            return {
                "exists": False,
                "lines": [],
                "updated_at": None,
                "source": "none",
            }

        lines = (
            [
                line
                for line in completed.stdout.splitlines()
                if line.strip() and line.strip() != "-- No entries --"
            ]
            if completed.returncode == 0
            else []
        )
        if not lines:
            return {
                "exists": False,
                "lines": [],
                "updated_at": None,
                "source": "none",
            }
        updated_at = None
        try:
            updated_at = datetime.fromisoformat(lines[-1].split(maxsplit=1)[0]).timestamp()
        except (ValueError, IndexError):
            # Keep logs available for unexpected journal formats. Leaving the
            # timestamp unset also keeps identical polls stable in the UI.
            pass
        return {
            "exists": True,
            "lines": lines[-bounded_limit:],
            "updated_at": updated_at,
            "source": "journal",
        }

    def stats(self) -> dict[str, Any]:
        if not self.path.is_file():
            return {"exists": False, "total": 0, "active": 0}
        try:
            with self._connect() as connection:
                row = connection.execute(
                    """
                    SELECT
                        COUNT(*) AS total,
                        SUM(CASE WHEN status = 'active' THEN 1 ELSE 0 END) AS active
                    FROM conversations
                    """
                ).fetchone()
        except (FileNotFoundError, sqlite3.Error):
            return {"exists": False, "total": 0, "active": 0}
        return {
            "exists": True,
            "total": int(row["total"] or 0),
            "active": int(row["active"] or 0),
        }

    def change_token(self) -> str:
        """Cheap token that changes when SQLite/WAL or synced logs change."""
        parts: list[str] = []
        targets = (
            self.path,
            Path(f"{self.path}-wal"),
            self.log_path,
        )
        for target in targets:
            try:
                stat = target.stat()
            except OSError:
                parts.append("0:0")
                continue
            parts.append(f"{stat.st_mtime_ns}:{stat.st_size}")
        return "|".join(parts)


def _schedule_job_name(prompt: str) -> str:
    words = re.findall(r"[a-z0-9]+", prompt.casefold())[:6]
    slug = "-".join(words) or "job"
    digest = hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()[:6]
    return f"ui-{slug[:36]}-{digest}"


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
    ) -> None:
        self._sender = sender
        self._sleep = sleeper
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
        temporary.write_text(
            json.dumps({"jobs": list(self._recoverable.values())}, ensure_ascii=False),
            encoding="utf-8",
        )
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
        retry_at: float,
        retry_attempt: int,
        created_at: float,
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
            "retry_at": retry_at,
            "retry_attempt": retry_attempt,
            "created_at": created_at,
        }
        with self._recovery_lock:
            self._recoverable[send_id] = record
            self._write_recovery_locked()

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
                retry_attempt = max(1, int(candidate.get("retry_attempt") or 1))
                created_at = float(candidate.get("created_at") or now)
            except (TypeError, ValueError):
                continue
            if not send_id or operation not in {"once", "reply"}:
                continue
            record = {
                "send_id": send_id,
                "operation": operation,
                "message": message,
                "conversation_id": conversation_id,
                "attachments": attachments,
                "client_id": client_id,
                "retry_at": retry_at,
                "retry_attempt": retry_attempt,
                "created_at": created_at,
            }
            self._recoverable[send_id] = record
            remaining = max(0.0, retry_at - now)
            self._jobs[send_id] = {
                "send_id": send_id,
                "operation": operation,
                "status": "rate_limited",
                "conversation_id": conversation_id,
                "error": "ChatGPT rate limited this account",
                "created_at": created_at,
                "updated_at": now,
                "attachment_count": len(attachments),
                "retry_at": retry_at,
                "retry_after_seconds": max(0, math.ceil(remaining)),
                "retry_attempt": retry_attempt,
            }
            if client_id:
                self._client_jobs[client_id] = send_id
            max_retry_at = max(max_retry_at, retry_at)
            max_attempt = max(max_attempt, retry_attempt)
            restored.append(record)

        if max_attempt:
            with self._rate_limit_lock:
                self._rate_limit_backoff.restore(
                    {
                        "attempts": max_attempt,
                        "blocked_until_epoch": max_retry_at,
                        "last_limited_at_epoch": now,
                    }
                )
        if restored:
            self._revision += 1
            logger.info("Restoring %d rate-limited Prompta UI send(s)", len(restored))
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
        else:
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
        send_id = uuid.uuid4().hex
        job = {
            "send_id": send_id,
            "operation": operation,
            "status": "queued",
            "conversation_id": conversation_id,
            "error": "",
            "created_at": now,
            "updated_at": now,
            "attachment_count": len(attachments or []),
        }
        with self._lock:
            cutoff = now - 3600.0
            self._jobs = {
                key: value
                for key, value in self._jobs.items()
                if float(value.get("updated_at") or 0.0) >= cutoff
            }
            live_send_ids = set(self._jobs)
            self._client_jobs = {
                key: value for key, value in self._client_jobs.items() if value in live_send_ids
            }
            if normalized_client_id:
                existing_send_id = self._client_jobs.get(normalized_client_id)
                existing = self._jobs.get(existing_send_id or "")
                if existing is not None:
                    self._cleanup_attachments(list(attachments or []))
                    return dict(existing)
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
                list(attachments or []),
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
                        retry_at=retry_at,
                        retry_attempt=max(1, attempt),
                        created_at=float(current.get("created_at") or time.time()),
                    )
                    self._sleep(remaining)

                self._update(
                    send_id,
                    status="running",
                    error="",
                    retry_at=0.0,
                    retry_after_seconds=0,
                )
                self._forget_recoverable(send_id)
                try:
                    result = self._sender(operation, message, conversation_id, attachments)
                except Exception as exc:
                    rate_limit = self._as_rate_limit_error(exc)
                    if rate_limit is None:
                        logger.exception(
                            "Prompta UI background send failed send_id=%s operation=%s conversation=%s",
                            send_id,
                            operation,
                            conversation_id or "new",
                        )
                        self._update(send_id, status="failed", error=str(exc))
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
                        retry_at=retry_at,
                        retry_attempt=attempt,
                        created_at=float(current.get("created_at") or time.time()),
                    )
                    self._sleep(delay)
                    continue

                self._reset_rate_limit_backoff()
                self._update(
                    send_id,
                    status="succeeded",
                    conversation_id=result,
                    error="",
                    retry_at=0.0,
                    retry_after_seconds=0,
                )
                return
        finally:
            self._cleanup_attachments(attachments)


class PromptaUIServer(ThreadingHTTPServer):
    """Single-host Prompta UI bound to the local Nox worker and cache."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        store: ReadOnlyChatStore,
        state_path: Path = DEFAULT_STATE_PATH,
        jobs_path: Path = DEFAULT_JOBS_PATH,
    ) -> None:
        super().__init__(address, PromptaUIHandler)
        self.store = store
        self.state_path = state_path.expanduser()
        self.jobs_path = jobs_path.expanduser()
        self.host_name = "nox"
        self._local_send_lock = threading.Lock()
        self.send_jobs = SendJobRegistry(
            self._send,
            recovery_path=self.state_path.parent / "ui-send-retries.json",
        )

    @property
    def display_name(self) -> str:
        return "Nox"

    def event_token(self) -> str:
        return f"{self.store.change_token()}|send:{self.send_jobs.revision}"

    def conversations(self, *, limit: int = 200, query: str = "") -> list[dict[str, Any]]:
        return self.store.conversations(limit=limit, query=query)

    def conversation(self, conversation_id: str) -> dict[str, Any] | None:
        return self.store.conversation(conversation_id)

    def send_job(self, send_id: str) -> dict[str, Any] | None:
        return self.send_jobs.get(send_id)

    def logs(self, *, limit: int = 500) -> dict[str, Any]:
        return self.store.logs(limit=limit)

    def save_attachments(self, raw_attachments: Any) -> list[str]:
        if raw_attachments is None:
            return []
        if not isinstance(raw_attachments, list) or len(raw_attachments) > 5:
            raise ValueError("Attachments must be a list of at most 5 files")

        upload_dir = self.state_path.parent / "ui-uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        total_bytes = 0
        try:
            for item in raw_attachments:
                if not isinstance(item, dict):
                    raise ValueError("Invalid attachment")
                name = Path(str(item.get("name") or "attachment")).name
                name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .") or "attachment"
                encoded = str(item.get("data") or "")
                if encoded.startswith("data:") and "," in encoded:
                    encoded = encoded.split(",", 1)[1]
                try:
                    content = base64.b64decode(encoded, validate=True)
                except (ValueError, binascii.Error) as exc:
                    raise ValueError(f"Attachment {name} is not valid base64") from exc
                total_bytes += len(content)
                if total_bytes > 25 * 1024 * 1024:
                    raise ValueError("Attachments exceed the 25 MB Prompta upload limit")
                target = upload_dir / f"{uuid.uuid4().hex}-{name}"
                target.write_bytes(content)
                target.chmod(0o600)
                saved.append(str(target))
        except Exception:
            for target in saved:
                Path(target).unlink(missing_ok=True)
            raise
        return saved

    def schedule_every(self, prompt: str, interval_minutes: float) -> dict[str, Any]:
        interval_minutes = float(interval_minutes)
        if not math.isfinite(interval_minutes):
            raise ValueError("Schedule interval must be finite")
        interval_minutes = max(0.1, min(interval_minutes, 60.0 * 24.0 * 30.0))
        name = _schedule_job_name(prompt)
        interval_seconds = interval_minutes * 60.0
        add_job(
            self.jobs_path,
            name,
            prompt,
            interval_seconds,
            exact_interval=True,
        )
        scheduler_started = _start_local_scheduler_service()
        return {
            "name": name,
            "prompt": prompt,
            "interval_minutes": interval_minutes,
            "scheduler_started": scheduler_started,
            "server": self.host_name,
        }

    def schedule_at(self, prompt: str, run_at_epoch: float) -> dict[str, Any]:
        run_at_epoch = float(run_at_epoch)
        if not math.isfinite(run_at_epoch) or run_at_epoch <= time.time():
            raise ValueError("Schedule time must be a finite timestamp in the future")
        name = f"at-{int(run_at_epoch)}-{hashlib.sha256(prompt.encode('utf-8')).hexdigest()[:10]}"
        add_job(
            self.jobs_path,
            name,
            prompt,
            0.0,
            exact_interval=True,
            run_at_epoch=run_at_epoch,
        )
        scheduler_started = _start_local_scheduler_service()
        return {
            "name": name,
            "prompt": prompt,
            "run_at_epoch": run_at_epoch,
            "scheduler_started": scheduler_started,
            "server": self.host_name,
        }

    def _send(
        self,
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str] | None = None,
    ) -> str:
        attachment_paths = list(attachments or [])
        with self._local_send_lock:
            scheduler_running = _wait_for_local_scheduler(self.state_path)
            if not scheduler_running and _start_local_scheduler_service():
                scheduler_running = _wait_for_local_scheduler(self.state_path)
            if not scheduler_running:
                raise RuntimeError(
                    "Prompta backend is unavailable after starting prompta.service"
                )
            if operation == "once":
                return asyncio.run(
                    _send_once_via_control(self.state_path, message, attachment_paths)
                )
            return asyncio.run(
                _send_reply_via_control(
                    self.state_path,
                    conversation_id,
                    message,
                    attachment_paths,
                )
            )


class PromptaUIHandler(BaseHTTPRequestHandler):
    server_version = "PromptaUI/1"

    def log_message(self, format: str, *args: Any) -> None:
        logger.debug("%s - %s", self.address_string(), format % args)

    @property
    def store(self) -> ReadOnlyChatStore:
        return cast(PromptaUIServer, self.server).store

    @property
    def state_path(self) -> Path:
        return cast(PromptaUIServer, self.server).state_path

    def _json_body(self) -> dict[str, Any] | None:
        content_type = self.headers.get("Content-Type", "")
        if not content_type.casefold().startswith("application/json"):
            self._json({"error": "Expected application/json"}, HTTPStatus.UNSUPPORTED_MEDIA_TYPE)
            return None
        try:
            content_length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            content_length = 0
        if content_length <= 0 or content_length > 36 * 1024 * 1024:
            self._json({"error": "Invalid request size"}, HTTPStatus.BAD_REQUEST)
            return None
        try:
            payload = json.loads(self.rfile.read(content_length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self._json({"error": "Invalid JSON body"}, HTTPStatus.BAD_REQUEST)
            return None
        if not isinstance(payload, dict):
            self._json({"error": "Expected a JSON object"}, HTTPStatus.BAD_REQUEST)
            return None
        return payload

    def _send_payload_from_json_body(self) -> tuple[str, list[str], str] | None:
        payload = self._json_body()
        if payload is None:
            return None
        message = str(payload.get("message") or "")
        if not message.strip():
            self._json({"error": "Message is empty"}, HTTPStatus.BAD_REQUEST)
            return None
        try:
            attachments = cast(PromptaUIServer, self.server).save_attachments(
                payload.get("attachments")
            )
        except (ValueError, OSError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return None
        client_id = str(payload.get("client_id") or "").strip()
        return message, attachments, client_id

    def _headers(
        self,
        status: HTTPStatus,
        content_type: str,
        content_length: int | None = None,
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        if content_length is not None:
            self.send_header("Content-Length", str(content_length))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'; connect-src 'self'; "
            "font-src 'self'; base-uri 'none'; frame-ancestors 'none'",
        )
        self.end_headers()

    def _write_response(self, status: HTTPStatus, content_type: str, body: bytes) -> None:
        try:
            self._headers(status, content_type, len(body))
            if getattr(self, "command", "GET") != "HEAD":
                self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            logger.debug("Prompta UI client disconnected before response completed")

    def _json(
        self,
        payload: Any,
        status: HTTPStatus = HTTPStatus.OK,
        *,
        content_type: str = "application/json; charset=utf-8",
    ) -> None:
        body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode()
        self._write_response(status, content_type, body)

    def _manifest(self) -> None:
        server = cast(PromptaUIServer, self.server)
        app_name = f"Prompta · {server.display_name}"
        self._json(
            {
                "name": app_name,
                "short_name": f"Prompta {server.display_name}",
                "description": f"Prompta conversation UI for {server.display_name}",
                "id": "./",
                "start_url": "./",
                "scope": "./",
                "display": "standalone",
                "background_color": "#212121",
                "theme_color": "#212121",
                "icons": [
                    {
                        "src": "./icon.svg",
                        "sizes": "any",
                        "type": "image/svg+xml",
                        "purpose": "any maskable",
                    }
                ],
            },
            content_type="application/manifest+json; charset=utf-8",
        )

    def _static(self, relative_path: str, content_type: str | None = None) -> None:
        target = (_STATIC_ROOT / relative_path).resolve()
        try:
            target.relative_to(_STATIC_ROOT.resolve())
        except ValueError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        try:
            body = target.read_bytes()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        mime = content_type or mimetypes.guess_type(target.name)[0] or "application/octet-stream"
        self._write_response(
            HTTPStatus.OK,
            f"{mime}; charset=utf-8" if mime.startswith("text/") else mime,
            body,
        )

    def _event_headers(self) -> bool:
        try:
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache, no-transform")
            self.send_header("X-Accel-Buffering", "no")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            logger.debug("Prompta UI event client disconnected before response headers completed")
            return False
        return True

    def _events(self) -> None:
        server = cast(PromptaUIServer, self.server)
        if not self._event_headers():
            return

        last_token = ""
        last_heartbeat = 0.0
        try:
            self.wfile.write(b"retry: 1000\n\n")
            self.wfile.flush()
            while True:
                token = server.event_token()
                now = time.monotonic()
                if token != last_token:
                    payload = json.dumps(
                        {
                            "token": token,
                            "server": server.host_name,
                            "online": True,
                            "head": _UI_HEAD,
                        },
                        ensure_ascii=False,
                        separators=(",", ":"),
                    )
                    self.wfile.write(f"event: refresh\ndata: {payload}\n\n".encode())
                    self.wfile.flush()
                    last_token = token
                    last_heartbeat = now
                elif now - last_heartbeat >= 15.0:
                    self.wfile.write(b": keepalive\n\n")
                    self.wfile.flush()
                    last_heartbeat = now
                time.sleep(0.2)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            return

    def do_HEAD(self) -> None:
        if urlparse(self.path).path == "/api/events":
            self._event_headers()
            return
        self.do_GET()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        if path == "/":
            self._static("index.html", "text/html")
            return
        if path == "/app.css":
            self._static("app.css", "text/css")
            return
        if path == "/app.js":
            self._static("app.js", "text/javascript")
            return
        if path in {"/manifest.json", "/manifest.webmanifest"}:
            self._manifest()
            return
        if path == "/icon.svg":
            self._static("icon.svg", "image/svg+xml")
            return
        if path == "/sw.js":
            self._static("sw.js", "text/javascript")
            return
        if path == "/api/events":
            self._events()
            return
        if path == "/api/health":
            server = cast(PromptaUIServer, self.server)
            self._json({
                **self.store.stats(),
                "server": server.host_name,
                "online": True,
                "head": _UI_HEAD,
            })
            return
        if path == "/api/chats":
            query = parse_qs(parsed.query)
            search = query.get("q", [""])[0]
            try:
                limit = int(query.get("limit", ["200"])[0])
            except ValueError:
                limit = 200
            self._json({"chats": cast(PromptaUIServer, self.server).conversations(limit=limit, query=search)})
            return
        if path == "/api/logs":
            query = parse_qs(parsed.query)
            try:
                limit = int(query.get("limit", ["500"])[0])
            except ValueError:
                limit = 500
            self._json(cast(PromptaUIServer, self.server).logs(limit=limit))
            return
        send_prefix = "/api/sends/"
        if path.startswith(send_prefix):
            send_id = unquote(path[len(send_prefix) :]).strip("/")
            job = cast(PromptaUIServer, self.server).send_job(send_id)
            if job is None:
                self._json({"error": "Send not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(job)
            return
        prefix = "/api/chats/"
        if path.startswith(prefix):
            conversation_id = unquote(path[len(prefix) :])
            chat = cast(PromptaUIServer, self.server).conversation(conversation_id)
            if chat is None:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            self._json(chat)
            return
        self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path

        if path == "/api/schedule":
            payload = self._json_body()
            if payload is None:
                return
            prompt = str(payload.get("prompt") or "").strip()
            try:
                interval_minutes = float(str(payload.get("interval_minutes") or ""))
            except (TypeError, ValueError):
                interval_minutes = 0.0
            if not prompt:
                self._json({"error": "Schedule prompt is empty"}, HTTPStatus.BAD_REQUEST)
                return
            if not math.isfinite(interval_minutes) or interval_minutes <= 0:
                self._json({"error": "Schedule interval must be a finite value greater than zero"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                result = cast(PromptaUIServer, self.server).schedule_every(
                    prompt,
                    interval_minutes,
                )
            except Exception as exc:
                logger.exception("Prompta UI scheduling failed")
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._json({"ok": True, **result}, HTTPStatus.CREATED)
            return

        if path == "/api/schedule-at":
            payload = self._json_body()
            if payload is None:
                return
            prompt = str(payload.get("prompt") or "").strip()
            try:
                run_at_epoch = float(str(payload.get("run_at_epoch") or ""))
            except (TypeError, ValueError):
                run_at_epoch = 0.0
            if not prompt:
                self._json({"error": "Schedule prompt is empty"}, HTTPStatus.BAD_REQUEST)
                return
            if not math.isfinite(run_at_epoch) or run_at_epoch <= time.time():
                self._json({"error": "Schedule time must be a finite timestamp in the future"}, HTTPStatus.BAD_REQUEST)
                return
            try:
                result = cast(PromptaUIServer, self.server).schedule_at(prompt, run_at_epoch)
            except Exception as exc:
                logger.exception("Prompta UI one-time scheduling failed")
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._json({"ok": True, **result}, HTTPStatus.CREATED)
            return

        if path == "/api/chats":
            send_payload = self._send_payload_from_json_body()
            if send_payload is None:
                return
            message, attachments, client_id = send_payload
            job = cast(PromptaUIServer, self.server).send_jobs.submit(
                operation="once",
                message=message,
                attachments=attachments,
                client_id=client_id,
            )
            self._json({"ok": True, **job}, HTTPStatus.ACCEPTED)
            return

        prefix = "/api/chats/"
        suffix = "/messages"
        if not (path.startswith(prefix) and path.endswith(suffix)):
            self.send_error(HTTPStatus.NOT_FOUND)
            return

        conversation_id = unquote(path[len(prefix) : -len(suffix)]).strip("/")
        server = cast(PromptaUIServer, self.server)
        if not conversation_id or server.store.conversation(conversation_id) is None:
            self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
            return

        send_payload = self._send_payload_from_json_body()
        if send_payload is None:
            return
        message, attachments, client_id = send_payload

        job = server.send_jobs.submit(
            operation="reply",
            conversation_id=conversation_id,
            message=message,
            attachments=attachments,
            client_id=client_id,
        )
        job["conversation_id"] = conversation_id
        self._json({"ok": True, **job}, HTTPStatus.ACCEPTED)


def _start_local_scheduler_service() -> bool:
    """Ask systemd to own the local Firefox session when the service is available."""

    try:
        started = subprocess.run(
            ["systemctl", "--user", "start", "prompta.service"],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.TimeoutExpired):
        logger.warning("Could not start Prompta scheduler service", exc_info=True)
        return False
    if started.returncode != 0:
        detail = (started.stderr or started.stdout or "").strip()
        logger.info(
            "Prompta scheduler service could not be started%s",
            f": {detail[-500:]}" if detail else "",
        )
        return False
    return True


def _wait_for_local_scheduler(state_path: Path) -> bool:
    """Allow a systemd-style scheduler restart to reclaim its daemon lock."""

    for attempt in range(_DAEMON_RESTART_GRACE_CHECKS):
        if _daemon_is_running(state_path):
            return True
        if attempt + 1 < _DAEMON_RESTART_GRACE_CHECKS:
            time.sleep(_DAEMON_STARTUP_POLL_SECONDS)
    return False


def _reconcile_orphaned_local_chats(
    cache_path: Path,
    state_path: Path,
) -> int:
    for attempt in range(_DAEMON_STARTUP_CHECKS):
        if _daemon_is_running(state_path):
            return 0
        if attempt + 1 < _DAEMON_STARTUP_CHECKS:
            time.sleep(_DAEMON_STARTUP_POLL_SECONDS)
    cache = ChatCache(cache_path)
    try:
        return cache.mark_orphaned_active()
    finally:
        cache.close()


def serve(
    cache_path: Path,
    log_path: Path | None,
    host: str,
    port: int,
    state_path: Path = DEFAULT_STATE_PATH,
    jobs_path: Path = DEFAULT_JOBS_PATH,
    preserve_active: bool = False,
) -> None:
    orphaned = (
        0
        if preserve_active
        else _reconcile_orphaned_local_chats(cache_path, state_path)
    )
    if orphaned:
        logger.info(
            "Prompta UI marked %d orphaned local conversation(s) interrupted",
            orphaned,
        )
    store = ReadOnlyChatStore(cache_path, log_path)
    server = PromptaUIServer(
        (host, port),
        store,
        state_path,
        jobs_path,
    )
    logger.info("Prompta UI listening on http://%s:%d", host, port)
    logger.info("Reading cache %s in SQLite query-only mode", cache_path.expanduser())
    logger.info("Sending replies through the local prompta.service control socket")
    logger.info("Reading logs from %s", store.log_path)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Prompta's Nox conversation UI")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    parser.add_argument("--logs", type=Path)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--preserve-active",
        action="store_true",
        help="Leave scheduler-owned active cache rows untouched during UI-only restarts",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    serve(
        args.cache,
        args.logs,
        args.host,
        max(1, min(args.port, 65535)),
        args.state,
        args.jobs_file,
        args.preserve_active,
    )


if __name__ == "__main__":
    main()
