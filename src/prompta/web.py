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
import shlex
import socket
import sqlite3
import subprocess
import threading
import time
import uuid
from collections.abc import Callable
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, cast
from urllib.parse import parse_qs, unquote, urlparse

from .cache import DEFAULT_CACHE_PATH, ChatCache
from .core import (
    DEFAULT_JOBS_PATH,
    DEFAULT_STATE_PATH,
    _daemon_is_running,
    _send_direct,
    _send_once_via_control,
    _send_reply_via_control,
    add_job,
)

logger = logging.getLogger(__name__)
_STATIC_ROOT = Path(__file__).with_name("static")
_DAEMON_STARTUP_CHECKS = 10
_DAEMON_STARTUP_POLL_SECONDS = 0.1


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
            else self.path.with_name("prompta-glass.log")
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
                WHERE c.title LIKE ? COLLATE NOCASE
                   OR c.job_name LIKE ? COLLATE NOCASE
                   OR c.prompt LIKE ? COLLATE NOCASE
                   OR EXISTS (
                       SELECT 1 FROM messages sm
                       WHERE sm.conversation_id = c.id
                         AND sm.message_key NOT LIKE 'request-placeholder-%'
                         AND sm.content LIKE ? COLLATE NOCASE
                   )
            """
            needle = f"%{search}%"
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

        lines = completed.stdout.splitlines() if completed.returncode == 0 else []
        if not lines:
            return {
                "exists": False,
                "lines": [],
                "updated_at": None,
                "source": "none",
            }
        return {
            "exists": True,
            "lines": lines[-bounded_limit:],
            "updated_at": time.time(),
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


_REMOTE_CONTROL_TIMEOUT_SECONDS = 2 * 60 * 60 + 10 * 60
_HOST_STATUS_TTL_SECONDS = 5.0
_HOST_CHECK_TIMEOUT_SECONDS = 3.0


def _schedule_job_name(prompt: str) -> str:
    words = re.findall(r"[a-z0-9]+", prompt.casefold())[:6]
    slug = "-".join(words) or "job"
    digest = hashlib.sha256(prompt.strip().encode("utf-8")).hexdigest()[:6]
    return f"ui-{slug[:36]}-{digest}"


def _remote_control(
    control_host: str,
    *,
    operation: str,
    message: str,
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
from prompta.core import DEFAULT_STATE_PATH, _send_once_via_control, _send_reply_via_control

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
    else:
        result = asyncio.run(
            _send_reply_via_control(
                DEFAULT_STATE_PATH,
                payload["conversation_id"],
                payload["message"],
                payload.get("attachments") or [],
            )
        )
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

    def __init__(self, sender: Callable[[str, str, str, list[str]], str]) -> None:
        self._sender = sender
        self._jobs: dict[str, dict[str, Any]] = {}
        self._client_jobs: dict[str, str] = {}
        self._lock = threading.Lock()
        self._revision = 0

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
            args=(send_id, operation, message, conversation_id, list(attachments or [])),
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
    ) -> None:
        self._update(send_id, status="running")
        try:
            result = self._sender(operation, message, conversation_id, attachments)
        except Exception as exc:
            logger.exception(
                "Prompta UI background send failed send_id=%s operation=%s conversation=%s",
                send_id,
                operation,
                conversation_id or "new",
            )
            self._update(send_id, status="failed", error=str(exc))
            return
        finally:
            self._cleanup_attachments(attachments)
        self._update(
            send_id,
            status="succeeded",
            conversation_id=result,
            error="",
        )


class PromptaUIServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(
        self,
        address: tuple[str, int],
        store: ReadOnlyChatStore,
        state_path: Path = DEFAULT_STATE_PATH,
        control_host: str = "",
        jobs_path: Path = DEFAULT_JOBS_PATH,
        extra_nodes: list[tuple[str, ReadOnlyChatStore, str]] | None = None,
    ) -> None:
        super().__init__(address, PromptaUIHandler)
        self.store = store
        self.state_path = state_path.expanduser()
        self.jobs_path = jobs_path.expanduser()
        self.control_host = control_host.strip()
        self.host_name = self.control_host or socket.gethostname().split(".", 1)[0]
        self._local_send_lock = threading.Lock()
        self._host_status_lock = threading.Lock()
        self._host_status_checked_at = 0.0
        self._host_status_online = not bool(self.control_host)
        self.send_jobs = SendJobRegistry(self._send)
        self.extra_nodes: dict[str, PromptaNodeTarget] = {}
        for node_name, node_store, node_control_host in extra_nodes or []:
            key = node_name.strip().casefold()
            if not key or key == self.host_name.casefold() or key in self.extra_nodes:
                continue
            self.extra_nodes[key] = PromptaNodeTarget(
                node_name.strip(),
                node_store,
                state_path,
                node_control_host,
                jobs_path,
            )

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

    def own_event_token(self) -> str:
        return (
            f"{self.store.change_token()}|send:{self.send_jobs.revision}"
            f"|online:{int(self.host_online())}"
        )

    def iter_nodes(self) -> list[Any]:
        return [self, *self.extra_nodes.values()]

    def event_token(self) -> str:
        return "||".join(
            f"{node.host_name}:{node.own_event_token()}"
            for node in self.iter_nodes()
        )

    def resolve_conversation(self, public_id: str) -> tuple[Any, str]:
        if "::" in public_id:
            prefix, actual_id = public_id.split("::", 1)
            target = self.extra_nodes.get(prefix.casefold())
            if target is not None and actual_id:
                return target, actual_id
        return self, public_id

    def public_conversation_id(self, target: Any, conversation_id: str) -> str:
        if target is self:
            return conversation_id
        return f"{target.host_name}::{conversation_id}"

    def conversations(self, *, limit: int = 200, query: str = "") -> list[dict[str, Any]]:
        merged: list[dict[str, Any]] = []
        per_node_limit = max(1, min(limit, 500))
        for target in self.iter_nodes():
            try:
                rows = target.store.conversations(limit=per_node_limit, query=query)
            except (FileNotFoundError, sqlite3.Error):
                logger.warning("Prompta UI node=%s cache unavailable", target.host_name, exc_info=True)
                continue
            for row in rows:
                item = dict(row)
                item["id"] = self.public_conversation_id(target, str(item.get("id") or ""))
                item["node"] = target.host_name
                item["node_display"] = target.display_name
                merged.append(item)
        merged.sort(
            key=lambda item: (
                str(item.get("status") or "") == "active",
                float(item.get("updated_at") or 0.0),
            ),
            reverse=True,
        )
        return merged[:per_node_limit]

    def conversation(self, public_id: str) -> dict[str, Any] | None:
        target, actual_id = self.resolve_conversation(public_id)
        chat = target.store.conversation(actual_id)
        if chat is None:
            return None
        result = dict(chat)
        result["id"] = self.public_conversation_id(target, actual_id)
        result["source_id"] = actual_id
        result["node"] = target.host_name
        result["node_display"] = target.display_name
        return result

    def send_job(self, send_id: str) -> dict[str, Any] | None:
        for target in self.iter_nodes():
            job = target.send_jobs.get(send_id)
            if job is not None:
                result = dict(job)
                conversation_id = str(result.get("conversation_id") or "")
                if conversation_id:
                    result["conversation_id"] = self.public_conversation_id(target, conversation_id)
                result["node"] = target.host_name
                return result
        return None

    def combined_logs(self, *, limit: int = 500) -> dict[str, Any]:
        lines: list[str] = []
        updated_at = 0.0
        exists = False
        nodes = self.iter_nodes()
        for target in nodes:
            try:
                payload = target.store.logs(limit=max(50, limit // max(1, len(nodes))))
            except Exception:
                continue
            exists = exists or bool(payload.get("exists"))
            updated_at = max(updated_at, float(payload.get("updated_at") or 0.0))
            prefix = f"[{target.display_name}] "
            lines.extend(prefix + str(line) for line in payload.get("lines") or [])
        return {
            "exists": exists,
            "source": "nodes",
            "lines": lines[-max(1, min(limit, 5000)):],
            "updated_at": updated_at,
        }

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

        if self.control_host:
            payload = base64.urlsafe_b64encode(
                json.dumps(
                    {
                        "name": name,
                        "prompt": prompt,
                        "interval_seconds": interval_seconds,
                    },
                    ensure_ascii=False,
                ).encode("utf-8")
            ).decode("ascii")
            code = """
import base64
import json
import subprocess
import sys
from prompta.core import DEFAULT_JOBS_PATH, add_job

payload = json.loads(base64.urlsafe_b64decode(sys.argv[1]).decode("utf-8"))
add_job(
    DEFAULT_JOBS_PATH,
    payload["name"],
    payload["prompt"],
    payload["interval_seconds"],
    exact_interval=True,
)
started = subprocess.run(
    ["systemctl", "--user", "start", "prompta.service"],
    check=False,
    capture_output=True,
    text=True,
).returncode == 0
print(json.dumps({"ok": True, "scheduler_started": started}))
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
                    self.control_host,
                    remote_command,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "remote scheduling failed").strip()
                raise RuntimeError(detail[-2000:])
            response_line = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
            try:
                response = json.loads(response_line)
            except json.JSONDecodeError as exc:
                raise RuntimeError("remote Prompta scheduling returned an invalid response") from exc
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise RuntimeError(str(response.get("error") or "remote Prompta scheduling failed"))
            scheduler_started = response.get("scheduler_started") is True
        else:
            add_job(
                self.jobs_path,
                name,
                prompt,
                interval_seconds,
                exact_interval=True,
            )
            started = subprocess.run(
                ["systemctl", "--user", "start", "prompta.service"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            scheduler_started = started.returncode == 0

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

        if self.control_host:
            payload = base64.urlsafe_b64encode(
                json.dumps(
                    {"name": name, "prompt": prompt, "run_at_epoch": run_at_epoch},
                    ensure_ascii=False,
                ).encode("utf-8")
            ).decode("ascii")
            code = """
import base64
import json
import subprocess
import sys
from prompta.core import DEFAULT_JOBS_PATH, add_job

payload = json.loads(base64.urlsafe_b64decode(sys.argv[1]).decode("utf-8"))
add_job(
    DEFAULT_JOBS_PATH,
    payload["name"],
    payload["prompt"],
    0.0,
    exact_interval=True,
    run_at_epoch=payload["run_at_epoch"],
)
started = subprocess.run(
    ["systemctl", "--user", "start", "prompta.service"],
    check=False,
    capture_output=True,
    text=True,
).returncode == 0
print(json.dumps({"ok": True, "scheduler_started": started}))
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
                    self.control_host,
                    remote_command,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            if completed.returncode != 0:
                detail = (completed.stderr or completed.stdout or "remote scheduling failed").strip()
                raise RuntimeError(detail[-2000:])
            response_line = completed.stdout.strip().splitlines()[-1] if completed.stdout.strip() else ""
            try:
                response = json.loads(response_line)
            except json.JSONDecodeError as exc:
                raise RuntimeError("remote Prompta scheduling returned an invalid response") from exc
            if not isinstance(response, dict) or response.get("ok") is not True:
                raise RuntimeError(str(response.get("error") or "remote Prompta scheduling failed"))
            scheduler_started = response.get("scheduler_started") is True
        else:
            add_job(
                self.jobs_path,
                name,
                prompt,
                0.0,
                exact_interval=True,
                run_at_epoch=run_at_epoch,
            )
            started = subprocess.run(
                ["systemctl", "--user", "start", "prompta.service"],
                check=False,
                capture_output=True,
                text=True,
                timeout=10,
            )
            scheduler_started = started.returncode == 0

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
        if self.control_host:
            return _remote_control(
                self.control_host,
                operation=operation,
                message=message,
                conversation_id=conversation_id,
                attachments=attachment_paths,
            )
        with self._local_send_lock:
            if _daemon_is_running(self.state_path):
                if operation == "once":
                    return asyncio.run(_send_once_via_control(self.state_path, message, attachment_paths))
                return asyncio.run(
                    _send_reply_via_control(self.state_path, conversation_id, message, attachment_paths)
                )
            logger.info("Prompta scheduler is stopped; using a direct local browser send")
            return asyncio.run(
                _send_direct(
                    self.state_path,
                    self.store.path,
                    message,
                    conversation_id=conversation_id if operation == "reply" else "",
                    attachments=attachment_paths,
                )
            )


class PromptaNodeTarget:
    # Non-listening Prompta node exposed through the unified UI server.
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
        self.send_jobs = SendJobRegistry(self._send)

    display_name = PromptaUIServer.display_name
    host_online = PromptaUIServer.host_online
    own_event_token = PromptaUIServer.own_event_token
    schedule_every = PromptaUIServer.schedule_every
    schedule_at = PromptaUIServer.schedule_at
    _send = PromptaUIServer._send


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

    @property
    def control_host(self) -> str:
        return cast(PromptaUIServer, self.server).control_host

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
                            "online": server.host_online(),
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
            nodes = [
                {
                    "name": node.host_name,
                    "display_name": node.display_name,
                    "online": node.host_online(),
                    **node.store.stats(),
                }
                for node in server.iter_nodes()
            ]
            self._json({
                **self.store.stats(),
                "server": server.host_name,
                "online": all(bool(node["online"]) for node in nodes),
                "head": _UI_HEAD,
                "nodes": nodes,
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
            self._json(cast(PromptaUIServer, self.server).combined_logs(limit=limit))
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
        target, actual_conversation_id = server.resolve_conversation(conversation_id)
        if not conversation_id or target.store.conversation(actual_conversation_id) is None:
            self._json({"error": "Conversation not found"}, HTTPStatus.NOT_FOUND)
            return

        send_payload = self._send_payload_from_json_body()
        if send_payload is None:
            return
        message, attachments, client_id = send_payload

        job = target.send_jobs.submit(
            operation="reply",
            conversation_id=actual_conversation_id,
            message=message,
            attachments=attachments,
            client_id=client_id,
        )
        job["conversation_id"] = conversation_id
        job["node"] = target.host_name
        self._json({"ok": True, **job}, HTTPStatus.ACCEPTED)


def _reconcile_orphaned_local_chats(
    cache_path: Path,
    state_path: Path,
    control_host: str,
) -> int:
    if control_host:
        return 0
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
    control_host: str = "",
    jobs_path: Path = DEFAULT_JOBS_PATH,
    preserve_active: bool = False,
    node_specs: list[str] | None = None,
) -> None:
    orphaned = (
        0
        if preserve_active
        else _reconcile_orphaned_local_chats(cache_path, state_path, control_host)
    )
    if orphaned:
        logger.info(
            "Prompta UI marked %d orphaned local conversation(s) interrupted",
            orphaned,
        )
    store = ReadOnlyChatStore(cache_path, log_path)
    extra_nodes: list[tuple[str, ReadOnlyChatStore, str]] = []
    for spec in node_specs or []:
        name, separator, rest = spec.partition("=")
        if not separator or not name.strip() or not rest.strip():
            raise ValueError("--node must be NAME=CACHE[,CONTROL_HOST[,LOG_PATH]]")
        parts = [part.strip() for part in rest.split(",", 2)]
        node_cache = Path(parts[0]).expanduser()
        node_control = parts[1] if len(parts) > 1 else ""
        node_logs = Path(parts[2]).expanduser() if len(parts) > 2 and parts[2] else None
        extra_nodes.append((name.strip(), ReadOnlyChatStore(node_cache, node_logs), node_control))
    server = PromptaUIServer(
        (host, port),
        store,
        state_path,
        control_host,
        jobs_path,
        extra_nodes=extra_nodes,
    )
    logger.info("Prompta UI listening on http://%s:%d", host, port)
    logger.info("Reading cache %s in SQLite query-only mode", cache_path.expanduser())
    if control_host:
        logger.info("Sending replies through Prompta on SSH host %s", control_host)
    else:
        logger.info(
            "Sending replies locally via scheduler control when available, direct browser otherwise"
        )
    logger.info("Reading logs from %s", store.log_path)
    try:
        server.serve_forever(poll_interval=0.25)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Serve Prompta's local conversation UI")
    parser.add_argument("--cache", type=Path, default=DEFAULT_CACHE_PATH)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE_PATH)
    parser.add_argument("--control-host", default="")
    parser.add_argument("--jobs-file", type=Path, default=DEFAULT_JOBS_PATH)
    parser.add_argument("--logs", type=Path)
    parser.add_argument(
        "--node",
        action="append",
        default=[],
        metavar="NAME=CACHE[,CONTROL_HOST[,LOG_PATH]]",
        help="Expose another Prompta node in this UI; may be repeated",
    )
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument(
        "--preserve-active",
        action="store_true",
        help="Leave active cache rows untouched when another Prompta UI owns them",
    )
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    serve(
        args.cache,
        args.logs,
        args.host,
        max(1, min(args.port, 65535)),
        args.state,
        args.control_host,
        args.jobs_file,
        args.preserve_active,
        args.node,
    )


if __name__ == "__main__":
    main()
