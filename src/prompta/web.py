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
import os
import re
import shlex
import sqlite3
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Callable
from datetime import datetime
from html import escape as html_escape
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
    _stop_via_control,
    _sync_via_control,
    add_job,
    is_rate_limited_text,
    load_jobs,
    parse_retry_after,
)

logger = logging.getLogger(__name__)
_STATIC_ROOT = Path(__file__).with_name("static")
_DAEMON_STARTUP_CHECKS = 10
_DAEMON_STARTUP_POLL_SECONDS = 0.1
_DAEMON_RESTART_GRACE_CHECKS = 120
_REMOTE_CONTROL_TIMEOUT_SECONDS = 11 * 60
_HOST_STATUS_TTL_SECONDS = 5.0
_HOST_CHECK_TIMEOUT_SECONDS = 3.0


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

    def event_fingerprint(self) -> str:
        """Compatibility token for older SSE consumers."""
        return self.change_token()


def _schedule_job_name(prompt: str) -> str:
    words = re.findall(r"[a-z0-9]+", prompt.casefold())[:6]
    slug = "-".join(words) or "job"
    digest = hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()[:6]
    return f"ui-{slug[:36]}-{digest}"


def _remote_control(
    control_host: str,
    *,
    operation: str,
    message: str = "",
    conversation_id: str = "",
    attachments: list[str] | None = None,
) -> str:
    remote_attachments: list[str] = []
    remote_dir = ""
    if attachments:
        remote_dir = f"/home/brandon/.local/state/prompta/ui-uploads/{uuid.uuid4().hex}"
        mkdir = subprocess.run(
            [
                "ssh",
                "-F",
                str(Path.home() / ".ssh" / "config"),
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                control_host,
                "mkdir",
                "-p",
                remote_dir,
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=20,
        )
        if mkdir.returncode != 0:
            raise RuntimeError((mkdir.stderr or "remote upload directory creation failed").strip())
        for index, attachment in enumerate(attachments):
            name = Path(attachment).name
            remote_path = f"{remote_dir}/{index}-{name}"
            copied = subprocess.run(
                [
                    "scp",
                    "-F",
                    str(Path.home() / ".ssh" / "config"),
                    "-q",
                    "-o",
                    "BatchMode=yes",
                    "-o",
                    "ConnectTimeout=8",
                    attachment,
                    f"{control_host}:{remote_path}",
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=120,
            )
            if copied.returncode != 0:
                subprocess.run(
                    ["ssh", "-F", str(Path.home() / ".ssh" / "config"), control_host, "rm", "-rf", remote_dir],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                raise RuntimeError((copied.stderr or "remote attachment transfer failed").strip())
            remote_attachments.append(remote_path)

    payload = base64.urlsafe_b64encode(
        json.dumps(
            {
                "operation": operation,
                "message": message,
                "conversation_id": conversation_id,
                "attachments": remote_attachments,
            },
            ensure_ascii=False,
        ).encode("utf-8")
    ).decode("ascii")
    code = """
import asyncio
import base64
import json
import sys
from prompta.core import DEFAULT_STATE_PATH, _send_once_via_control, _send_reply_via_control, _stop_via_control, _sync_via_control

payload = json.loads(base64.urlsafe_b64decode(sys.argv[1]).decode("utf-8"))
try:
    if payload["operation"] == "once":
        result = asyncio.run(
            _send_once_via_control(
                DEFAULT_STATE_PATH,
                payload["message"],
                payload.get("attachments") or [],
            )
        )
    elif payload["operation"] == "reply":
        result = asyncio.run(
            _send_reply_via_control(
                DEFAULT_STATE_PATH,
                payload["conversation_id"],
                payload["message"],
                payload.get("attachments") or [],
            )
        )
    elif payload["operation"] == "stop":
        result = asyncio.run(
            _stop_via_control(DEFAULT_STATE_PATH, payload["conversation_id"])
        )
    elif payload["operation"] == "sync":
        result = asyncio.run(
            _sync_via_control(DEFAULT_STATE_PATH, payload["conversation_id"])
        )
    else:
        raise RuntimeError("unsupported remote Prompta control operation")
except Exception as exc:
    print(json.dumps({"ok": False, "error": str(exc)}, ensure_ascii=False))
else:
    print(json.dumps({"ok": True, "conversation_id": result}, ensure_ascii=False))
""".strip()
    remote_command = shlex.join(
        ["/home/brandon/prompta/.venv/bin/python", "-c", code, payload]
    )
    completed = subprocess.run(
        [
            "ssh",
            "-F",
            str(Path.home() / ".ssh" / "config"),
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=8",
            control_host,
            remote_command,
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=_REMOTE_CONTROL_TIMEOUT_SECONDS,
    )
    if completed.returncode != 0:
        if remote_dir:
            subprocess.run(
                ["ssh", "-F", str(Path.home() / ".ssh" / "config"), control_host, "rm", "-rf", remote_dir],
                check=False,
                capture_output=True,
                text=True,
                timeout=15,
            )
        detail = (completed.stderr or completed.stdout or "remote control failed").strip()
        raise RuntimeError(detail[-2000:])
    if remote_dir:
        subprocess.run(
            ["ssh", "-F", str(Path.home() / ".ssh" / "config"), control_host, "rm", "-rf", remote_dir],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    result = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
    if not result:
        raise RuntimeError("remote Prompta control returned an empty conversation id")
    try:
        response = json.loads(result)
    except json.JSONDecodeError:
        return result
    if not isinstance(response, dict):
        raise RuntimeError("remote Prompta control returned an invalid response")
    if response.get("ok") is not True:
        raise RuntimeError(str(response.get("error") or "remote Prompta control failed"))
    conversation_id = str(response.get("conversation_id") or "")
    if not conversation_id:
        raise RuntimeError("remote Prompta control returned an empty conversation id")
    return conversation_id


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
                retry_attempt = max(0, int(candidate.get("retry_attempt") or 0))
                created_at = float(candidate.get("created_at") or now)
            except (TypeError, ValueError):
                continue
            if not send_id or operation not in {"once", "reply"}:
                continue
            status = str(candidate.get("status") or "").strip()
            if not status:
                status = "rate_limited" if retry_at > 0 or retry_attempt > 0 else "queued"
            if status not in {"queued", "running", "rate_limited"}:
                status = "queued"
            restored_status = "rate_limited" if status == "rate_limited" else "queued"
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
            self._recoverable[send_id] = record
            remaining = max(0.0, retry_at - now) if restored_status == "rate_limited" else 0.0
            self._jobs[send_id] = {
                "send_id": send_id,
                "operation": operation,
                "status": restored_status,
                "conversation_id": conversation_id,
                "error": "ChatGPT rate limited this account" if restored_status == "rate_limited" else "",
                "created_at": created_at,
                "updated_at": now,
                "attachment_count": len(attachments),
                "retry_at": retry_at if restored_status == "rate_limited" else 0.0,
                "retry_after_seconds": max(0, math.ceil(remaining)),
                "retry_attempt": retry_attempt if restored_status == "rate_limited" else 0,
            }
            if client_id:
                self._client_jobs[client_id] = send_id
            if restored_status == "rate_limited":
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
            # Several durable-send workers can already be inside the scheduler
            # when the first request discovers a ChatGPT rate limit. They are
            # all observing the same limit window, so do not count each worker
            # as a separate failed retry and exponentially amplify the backoff.
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
                        self._forget_recoverable(send_id)
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
                        created_at=float(current.get("created_at") or time.time()),
                        status="rate_limited",
                        retry_at=retry_at,
                        retry_attempt=attempt,
                    )
                    self._sleep(delay)
                    continue

                self._reset_rate_limit_backoff()
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
                self._forget_recoverable(send_id)
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
    """Prompta UI with one local node and optional remote cache/control nodes."""

    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        store: ReadOnlyChatStore,
        state_path: Path = DEFAULT_STATE_PATH,
        jobs_path: Path = DEFAULT_JOBS_PATH,
        *,
        control_host: str = "",
        server_name: str = "",
        extra_nodes: list[tuple[str, ReadOnlyChatStore, str]] | None = None,
    ) -> None:
        super().__init__(address, PromptaUIHandler)
        self.store = store
        self.state_path = state_path.expanduser()
        self.jobs_path = jobs_path.expanduser()
        self.control_host = control_host.strip()
        self._explicit_server_name = bool(server_name.strip())
        self.host_name = (server_name.strip() or self.control_host or "nox").split(".", 1)[0]
        self._local_send_lock = threading.Lock()
        self._host_status_lock = threading.Lock()
        self._host_status_checked_at = 0.0
        self._host_status_online = not bool(self.control_host)
        self._image_preview_lock = threading.Lock()
        self._image_preview_path = self.state_path.parent / "ui-image-previews.json"
        self._image_preview_dir = self.state_path.parent / "ui-image-previews"
        self._image_previews = self._load_image_previews()
        self.send_jobs = SendJobRegistry(
            self._send,
            recovery_path=self.state_path.parent / "ui-send-retries.json",
            on_success=self._bind_image_previews,
        )
        self.extra_nodes: dict[str, PromptaNodeTarget] = {}
        for node_name, node_store, node_control_host in extra_nodes or []:
            normalized = str(node_name).strip()
            if not normalized or normalized == self.host_name:
                continue
            self.extra_nodes[normalized] = PromptaNodeTarget(
                normalized,
                node_store,
                self.state_path,
                str(node_control_host),
                self.jobs_path,
            )

    def _load_image_previews(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self._image_preview_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return {}
        records = payload.get("records", {}) if isinstance(payload, dict) else {}
        if not isinstance(records, dict):
            return {}
        cutoff = time.time() - (30 * 24 * 60 * 60)
        cleaned: dict[str, dict[str, Any]] = {}
        for client_id, raw_record in records.items():
            if not isinstance(raw_record, dict):
                continue
            try:
                created_at = float(raw_record.get("created_at") or 0.0)
            except (TypeError, ValueError):
                created_at = 0.0
            conversation_id = str(raw_record.get("conversation_id") or "")
            if not conversation_id and created_at and created_at < cutoff:
                continue
            images = raw_record.get("images")
            if not isinstance(images, list):
                continue
            kept_images = []
            for image in images:
                if not isinstance(image, dict):
                    continue
                preview_id = str(image.get("id") or "")
                if not preview_id:
                    continue
                file_path = self._image_preview_dir / preview_id
                if not file_path.is_file():
                    continue
                kept_images.append(
                    {
                        "id": preview_id,
                        "name": str(image.get("name") or "image"),
                        "type": str(image.get("type") or "image/*"),
                    }
                )
            if kept_images:
                cleaned[str(client_id)] = {
                    "client_id": str(client_id),
                    "conversation_id": conversation_id,
                    "message": str(raw_record.get("message") or ""),
                    "created_at": created_at or time.time(),
                    "images": kept_images,
                }
        return cleaned

    def _write_image_previews_locked(self) -> None:
        self._image_preview_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self._image_preview_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"records": self._image_previews}, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self._image_preview_path)

    def _replace_staged_image_previews(
        self,
        client_id: str,
        message: str,
        images: list[dict[str, str]],
    ) -> None:
        if not client_id or not images:
            return
        with self._image_preview_lock:
            previous = self._image_previews.get(client_id)
            if isinstance(previous, dict) and not previous.get("conversation_id"):
                for image in previous.get("images", []):
                    if isinstance(image, dict):
                        try:
                            (self._image_preview_dir / str(image.get("id") or "")).unlink(
                                missing_ok=True
                            )
                        except OSError:
                            pass
            self._image_previews[client_id] = {
                "client_id": client_id,
                "conversation_id": "",
                "message": message,
                "created_at": time.time(),
                "images": images,
            }
            self._write_image_previews_locked()

    def _bind_image_previews(self, client_id: str, conversation_id: str, message: str) -> None:
        with self._image_preview_lock:
            record = self._image_previews.get(client_id)
            if not isinstance(record, dict):
                return
            record["conversation_id"] = conversation_id
            if message:
                record["message"] = message
            self._write_image_previews_locked()

    def _enrich_image_previews(self, chat: dict[str, Any], conversation_id: str) -> None:
        messages = chat.get("messages")
        if not isinstance(messages, list):
            return
        with self._image_preview_lock:
            records = [
                dict(record)
                for record in self._image_previews.values()
                if isinstance(record, dict)
                and str(record.get("conversation_id") or "") == conversation_id
            ]
        records.sort(key=lambda record: float(record.get("created_at") or 0.0))
        used_indexes: set[int] = set()
        for record in records:
            expected = str(record.get("message") or "").strip()
            candidates = [
                (index, message)
                for index, message in enumerate(messages)
                if index not in used_indexes
                and isinstance(message, dict)
                and str(message.get("role") or "") == "user"
                and str(message.get("content") or "").strip() == expected
            ]
            if not candidates:
                continue
            record_created = float(record.get("created_at") or 0.0)
            index, message = min(
                candidates,
                key=lambda item: abs(float(item[1].get("created_at") or 0.0) - record_created),
            )
            used_indexes.add(index)
            images = record.get("images")
            if isinstance(images, list):
                message["attachments"] = [
                    {
                        "id": str(image.get("id") or ""),
                        "name": str(image.get("name") or "image"),
                        "type": str(image.get("type") or "image/*"),
                    }
                    for image in images
                    if isinstance(image, dict) and image.get("id")
                ]

    def image_preview(self, preview_id: str) -> tuple[bytes, str] | None:
        if not re.fullmatch(r"[a-f0-9]{32}", preview_id):
            return None
        media_type = "application/octet-stream"
        found = False
        with self._image_preview_lock:
            for record in self._image_previews.values():
                if not isinstance(record, dict):
                    continue
                for image in record.get("images", []):
                    if not isinstance(image, dict) or str(image.get("id") or "") != preview_id:
                        continue
                    media_type = str(image.get("type") or "application/octet-stream")
                    found = True
                    break
                if found:
                    break
        if not found:
            return None
        try:
            body = (self._image_preview_dir / preview_id).read_bytes()
        except OSError:
            return None
        return body, media_type

    @property
    def display_name(self) -> str:
        return self.host_name.replace("-", " ").replace("_", " ").title()

    def host_online(self, *, force: bool = False) -> bool:
        if not self.control_host:
            return True
        now = time.monotonic()
        with self._host_status_lock:
            if not force and now - self._host_status_checked_at < _HOST_STATUS_TTL_SECONDS:
                return self._host_status_online
            try:
                completed = subprocess.run(
                    [
                        "ssh",
                        "-F",
                        str(Path.home() / ".ssh" / "config"),
                        "-o",
                        "BatchMode=yes",
                        "-o",
                        "ConnectTimeout=2",
                        "-o",
                        "ConnectionAttempts=1",
                        self.control_host,
                        "true",
                    ],
                    check=False,
                    capture_output=True,
                    text=True,
                    timeout=_HOST_CHECK_TIMEOUT_SECONDS,
                )
                online = completed.returncode == 0
            except (OSError, subprocess.TimeoutExpired):
                online = False
            self._host_status_checked_at = time.monotonic()
            self._host_status_online = online
            return online

    def iter_nodes(self):
        yield self
        yield from self.extra_nodes.values()

    def resolve_conversation(self, public_id: str):
        node_name, separator, actual_id = public_id.partition("::")
        if separator:
            target = self.extra_nodes.get(node_name)
            if target is None:
                raise KeyError(public_id)
            return target, actual_id
        return self, public_id

    @staticmethod
    def _public_chat(target, chat: dict[str, Any], local_target) -> dict[str, Any]:
        result = dict(chat)
        actual_id = str(result.get("id") or "")
        if target is not local_target:
            result["id"] = f"{target.host_name}::{actual_id}"
        result["node"] = target.host_name
        result["node_display"] = target.display_name
        return result

    def event_token(self) -> str:
        parts = []
        for target in self.iter_nodes():
            parts.append(
                f"{target.host_name}:{target.store.change_token()}:"
                f"send={target.send_jobs.revision}:online={int(target.host_online())}"
            )
        return "|".join(parts)

    def conversations(self, *, limit: int = 200, query: str = "") -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for target in self.iter_nodes():
            rows.extend(
                self._public_chat(target, chat, self)
                for chat in target.store.conversations(limit=limit, query=query)
            )
        rows.sort(
            key=lambda chat: (
                0 if str(chat.get("status") or "") == "active" else 1,
                -float(chat.get("updated_at") or 0.0),
            )
        )
        return rows[: max(1, min(limit, 500))]

    def conversation(self, public_id: str) -> dict[str, Any] | None:
        try:
            target, actual_id = self.resolve_conversation(public_id)
        except KeyError:
            return None
        chat = target.store.conversation(actual_id)
        if chat is None:
            return None
        result = self._public_chat(target, chat, self)
        if target is self:
            self._enrich_image_previews(result, actual_id)
        return result

    def stop_conversation(self, public_id: str) -> str:
        target, actual_id = self.resolve_conversation(public_id)
        if target.store.conversation(actual_id) is None:
            raise KeyError(public_id)
        return target._stop(actual_id)

    def probe_conversation(self, public_id: str) -> tuple[dict[str, Any], int]:
        target, actual_id = self.resolve_conversation(public_id)
        if target.store.conversation(actual_id) is None:
            raise KeyError(public_id)
        message_count = target._sync(actual_id)
        chat = self.conversation(public_id)
        if chat is None:
            raise KeyError(public_id)
        return chat, message_count

    def send_job(self, send_id: str) -> dict[str, Any] | None:
        for target in self.iter_nodes():
            job = target.send_jobs.get(send_id)
            if job is not None:
                result = dict(job)
                conversation_id = str(result.get("conversation_id") or "")
                if conversation_id and target is not self:
                    result["conversation_id"] = f"{target.host_name}::{conversation_id}"
                return result
        return None

    def logs(self, *, limit: int = 500) -> dict[str, Any]:
        return self.store.logs(limit=limit)

    def scheduled_jobs(self) -> dict[str, Any]:
        try:
            state_payload = json.loads(self.state_path.read_text())
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            state_payload = {}
        state_jobs = state_payload.get("jobs") if isinstance(state_payload, dict) else {}
        if not isinstance(state_jobs, dict):
            state_jobs = {}

        jobs = []
        for job in load_jobs(self.jobs_path).values():
            job_state = state_jobs.get(job.name)
            if not isinstance(job_state, dict):
                job_state = {}
            paused = job_state.get("paused") is True
            status = "paused" if paused else str(job_state.get("status") or "pending")
            if status not in {"paused", "pending", "healthy", "failing", "rate-limited"}:
                status = "pending"
            try:
                next_due_at = float(job_state.get("next_due_at_epoch") or 0.0)
            except (TypeError, ValueError):
                next_due_at = 0.0
            jobs.append(
                {
                    "name": job.name,
                    "prompt": job.prompt,
                    "interval_minutes": job.interval_seconds / 60.0,
                    "daily_at": job.daily_at,
                    "run_at_epoch": job.run_at_epoch,
                    "exact_interval": job.exact_interval,
                    "paused": paused,
                    "status": status,
                    "next_due_at_epoch": next_due_at,
                }
            )
        return {"jobs": jobs, "server": self.host_name}

    def _run_job_cli(self, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        action = action.strip().lower()
        command = [sys.executable, "-m", "prompta.core"]

        if action == "add":
            name = str(payload.get("name") or "").strip()
            prompt = str(payload.get("prompt") or "").strip()
            if not name:
                raise ValueError("Job name is required")
            if not prompt:
                raise ValueError("Job prompt is required")
            command += ["add", name, prompt]
            daily_at = str(payload.get("daily_at") or "").strip()
            if daily_at:
                if not re.fullmatch(r"(?:[01]\d|2[0-3]):[0-5]\d", daily_at):
                    raise ValueError("Daily time must use HH:MM")
                command += ["--daily-at", daily_at]
            else:
                try:
                    interval_minutes = float(payload.get("interval_minutes"))
                except (TypeError, ValueError) as exc:
                    raise ValueError("Interval minutes must be a number") from exc
                if not math.isfinite(interval_minutes) or interval_minutes <= 0:
                    raise ValueError("Interval minutes must be greater than zero")
                command += ["--interval-minutes", str(interval_minutes)]
                if payload.get("exact_interval") is True:
                    command.append("--exact-interval")
            command += ["--jobs-file", str(self.jobs_path)]
        elif action in {"remove", "pause", "resume"}:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise ValueError("Job name is required")
            command += [action, name, "--jobs-file", str(self.jobs_path)]
            if action in {"pause", "resume"}:
                command += ["--state", str(self.state_path)]
        elif action == "clear":
            command += ["clear", "--jobs-file", str(self.jobs_path)]
        else:
            raise ValueError(f"Unsupported jobs command: {action}")

        completed = subprocess.run(
            command,
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout).strip()
            raise RuntimeError(detail or f"prompta {action} failed")

        if action in {"add", "resume"}:
            _start_local_scheduler_service()
        display = ["prompta", *command[3:]]
        return {
            "ok": True,
            "command": display,
            **self.scheduled_jobs(),
        }

    def save_attachments(
        self,
        raw_attachments: Any,
        *,
        client_id: str = "",
        message: str = "",
    ) -> list[str]:
        if raw_attachments is None:
            return []
        if not isinstance(raw_attachments, list) or len(raw_attachments) > 5:
            raise ValueError("Attachments must be a list of at most 5 files")

        upload_dir = self.state_path.parent / "ui-uploads"
        upload_dir.mkdir(parents=True, exist_ok=True)
        self._image_preview_dir.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        preview_files: list[Path] = []
        preview_images: list[dict[str, str]] = []
        total_bytes = 0
        try:
            for item in raw_attachments:
                if not isinstance(item, dict):
                    raise ValueError("Invalid attachment")
                name = Path(str(item.get("name") or "attachment")).name
                name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .") or "attachment"
                media_type = str(item.get("type") or "application/octet-stream").strip().lower()
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
                if client_id and media_type.startswith("image/"):
                    preview_id = uuid.uuid4().hex
                    preview_target = self._image_preview_dir / preview_id
                    preview_target.write_bytes(content)
                    preview_target.chmod(0o600)
                    preview_files.append(preview_target)
                    preview_images.append(
                        {"id": preview_id, "name": name, "type": media_type}
                    )
        except Exception:
            for target in saved:
                Path(target).unlink(missing_ok=True)
            for target in preview_files:
                target.unlink(missing_ok=True)
            raise
        if preview_images:
            self._replace_staged_image_previews(client_id, message, preview_images)
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


    def _stop(self, conversation_id: str) -> str:
        if self.control_host:
            return _remote_control(
                self.control_host,
                operation="stop",
                conversation_id=conversation_id,
            )
        if not _daemon_is_running(self.state_path):
            raise RuntimeError("Prompta scheduler is not running; cannot stop an active chat")
        return asyncio.run(_stop_via_control(self.state_path, conversation_id))

    def _sync(self, conversation_id: str) -> int:
        if self.control_host:
            return int(_remote_control(
                self.control_host,
                operation="sync",
                conversation_id=conversation_id,
            ))
        if not _daemon_is_running(self.state_path):
            raise RuntimeError("Prompta scheduler is not running; cannot inspect chat activity")
        return asyncio.run(_sync_via_control(self.state_path, conversation_id))

    def _send(
        self,
        operation: str,
        message: str,
        conversation_id: str,
        attachments: list[str] | None = None,
    ) -> str:
        attachment_paths = list(attachments or [])
        if self.control_host:
            return _remote_control(
                self.control_host,
                operation=operation,
                message=message,
                conversation_id=conversation_id,
                attachments=attachment_paths,
            )
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


class PromptaNodeTarget:
    """Non-listening Prompta node exposed through the unified UI server."""

    def __init__(
        self,
        host_name: str,
        store: ReadOnlyChatStore,
        state_path: Path,
        control_host: str,
        jobs_path: Path,
    ) -> None:
        self.store = store
        self.state_path = state_path.expanduser()
        self.jobs_path = jobs_path.expanduser()
        self.control_host = control_host.strip()
        self.host_name = host_name.strip()
        self._local_send_lock = threading.Lock()
        self._host_status_lock = threading.Lock()
        self._host_status_checked_at = 0.0
        self._host_status_online = not bool(self.control_host)
        self.send_jobs = SendJobRegistry(
            self._send,
            recovery_path=self.state_path.parent / f"ui-send-retries-{self.host_name}.json",
        )

    @property
    def display_name(self) -> str:
        return self.host_name.replace("-", " ").replace("_", " ").title()

    host_online = PromptaUIServer.host_online
    _send = PromptaUIServer._send
    _stop = PromptaUIServer._stop
    _sync = PromptaUIServer._sync


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
        client_id = str(payload.get("client_id") or "").strip()
        try:
            attachments = cast(PromptaUIServer, self.server).save_attachments(
                payload.get("attachments"),
                client_id=client_id,
                message=message,
            )
        except (ValueError, OSError) as exc:
            self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            return None
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
                "short_name": app_name if server._explicit_server_name else f"Prompta {server.display_name}",
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

    def _index(self) -> None:
        server = cast(PromptaUIServer, self.server)
        try:
            page = (_STATIC_ROOT / "index.html").read_text()
            display_name = html_escape(server.display_name)
            page = page.replace("__PROMPTA_SERVER_NAME__", display_name)
            page = page.replace(
                "<title>Prompta</title>",
                f"<title>Prompta · {display_name}</title>",
            )
            body = page.encode()
        except OSError:
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        self._write_response(HTTPStatus.OK, "text/html; charset=utf-8", body)




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
                            "online": server.host_online(),
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
            self._index()
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
        if path == "/api/events":
            self._event_stream()
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
        if path == "/api/jobs":
            self._json(cast(PromptaUIServer, self.server).scheduled_jobs())
            return
        preview_prefix = "/api/attachment-previews/"
        if path.startswith(preview_prefix):
            preview_id = unquote(path[len(preview_prefix) :]).strip("/")
            preview = cast(PromptaUIServer, self.server).image_preview(preview_id)
            if preview is None:
                self.send_error(HTTPStatus.NOT_FOUND)
                return
            body, media_type = preview
            self._write_response(HTTPStatus.OK, media_type, body)
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

        if path == "/api/jobs":
            payload = self._json_body()
            if payload is None:
                return
            action = str(payload.get("action") or "").strip().lower()
            try:
                result = cast(PromptaUIServer, self.server)._run_job_cli(action, payload)
            except ValueError as exc:
                self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
                return
            except Exception as exc:
                logger.exception("Prompta UI jobs command failed")
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._json(result)
            return

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
        probe_suffix = "/probe"
        if path.startswith(prefix) and path.endswith(probe_suffix):
            conversation_id = unquote(path[len(prefix) : -len(probe_suffix)]).strip("/")
            if not conversation_id:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                chat, message_count = cast(PromptaUIServer, self.server).probe_conversation(conversation_id)
            except KeyError:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            except Exception as exc:
                logger.exception("Prompta UI activity probe failed conversation=%s", conversation_id)
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._json({"ok": True, "chat": chat, "message_count": message_count})
            return

        stop_suffix = "/stop"
        if path.startswith(prefix) and path.endswith(stop_suffix):
            conversation_id = unquote(path[len(prefix) : -len(stop_suffix)]).strip("/")
            if not conversation_id:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            try:
                stopped_id = cast(PromptaUIServer, self.server).stop_conversation(conversation_id)
            except KeyError:
                self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
                return
            except Exception as exc:
                logger.exception("Prompta UI stop failed conversation=%s", conversation_id)
                self._json({"error": str(exc)}, HTTPStatus.BAD_GATEWAY)
                return
            self._json({"ok": True, "conversation_id": conversation_id, "stopped_id": stopped_id})
            return

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
