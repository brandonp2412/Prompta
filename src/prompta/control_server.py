from __future__ import annotations

import asyncio
import fcntl
import json
import logging
import os
from pathlib import Path
from typing import Any

from .rate_limit import RateLimitError

logger = logging.getLogger(__name__)

_CONTROL_SOCKET_NAME = "control.sock"
_DAEMON_LOCK_NAME = "daemon.lock"
_CONTROL_CONNECT_TIMEOUT_SECONDS = 30.0


class ControlUnavailableError(RuntimeError):
    """The scheduler control channel is unavailable before a request can be sent."""


def _control_socket_path(state_path: Path) -> Path:
    return state_path.expanduser().parent / _CONTROL_SOCKET_NAME


def _daemon_lock_path(state_path: Path) -> Path:
    return state_path.expanduser().parent / _DAEMON_LOCK_NAME


def _daemon_is_running(state_path: Path) -> bool:
    path = _daemon_lock_path(state_path)
    try:
        handle = path.open("r")
    except FileNotFoundError:
        return False
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        return True
    fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()
    return False


def _acquire_daemon_lock(state_path: Path) -> Any:
    path = _daemon_lock_path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+")
    os.chmod(path, 0o600)
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        handle.close()
        raise RuntimeError("another Prompta scheduler is already running") from exc
    return handle


async def _handle_control_client(
    prompta: Any,
    reader: asyncio.StreamReader,
    writer: asyncio.StreamWriter,
) -> None:
    try:
        raw = await asyncio.wait_for(reader.readline(), timeout=10.0)
        payload = json.loads(raw.decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError("invalid Prompta control request")
        op = str(payload.get("op") or "")
        if op == "sync":
            conversation_id = str(payload.get("conversation_id") or "")
            if not conversation_id.strip():
                raise ValueError("conversation id is empty")
            sync_future: asyncio.Future[int] = asyncio.get_running_loop().create_future()
            await prompta._sync_requests.put((conversation_id, sync_future))
            message_count = await sync_future
            response = {"ok": True, "message_count": message_count}
        elif op == "stop":
            conversation_id = str(payload.get("conversation_id") or "")
            if not conversation_id.strip():
                raise ValueError("conversation id is empty")
            stopped_id = await prompta.stop_conversation(conversation_id)
            response = {"ok": True, "conversation_id": stopped_id}
        else:
            prompt = str(payload.get("prompt") or "")
            raw_attachments = payload.get("attachments")
            attachments = (
                [str(path) for path in raw_attachments if isinstance(path, str) and path.strip()]
                if isinstance(raw_attachments, list)
                else []
            )
            if not prompt.strip() and not attachments:
                raise ValueError("prompta prompt is empty")
            future: asyncio.Future[str] = asyncio.get_running_loop().create_future()
            if op == "once":
                await prompta._once_requests.put((prompt, attachments, future))
            elif op == "reply":
                conversation_id = str(payload.get("conversation_id") or "")
                if not conversation_id.strip():
                    raise ValueError("conversation id is empty")
                await prompta._reply_requests.put((conversation_id, prompt, attachments, future))
            else:
                raise ValueError("unsupported Prompta control request")
            conversation_id = await future
            response = {"ok": True, "conversation_id": conversation_id}
    except RateLimitError as exc:
        response = {
            "ok": False,
            "error": str(exc),
            "error_type": "rate_limit",
            "retry_after": exc.retry_after,
        }
    except Exception as exc:
        response = {"ok": False, "error": str(exc)}
    try:
        writer.write((json.dumps(response, ensure_ascii=False) + "\n").encode("utf-8"))
        await writer.drain()
    except (BrokenPipeError, ConnectionResetError):
        logger.debug("Prompta control client disconnected before receiving its result")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except (BrokenPipeError, ConnectionResetError):
            pass


async def _start_control_server(
    prompta: Any,
    state_path: Path,
) -> tuple[asyncio.AbstractServer, Path]:
    path = _control_socket_path(state_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.unlink()
    except FileNotFoundError:
        pass
    server = await asyncio.start_unix_server(
        lambda reader, writer: _handle_control_client(prompta, reader, writer),
        path=str(path),
    )
    os.chmod(path, 0o600)
    return server, path


async def _open_control_connection(
    state_path: Path,
) -> tuple[asyncio.StreamReader, asyncio.StreamWriter]:
    path = _control_socket_path(state_path)
    deadline = asyncio.get_running_loop().time() + _CONTROL_CONNECT_TIMEOUT_SECONDS
    last_error: OSError | None = None
    while True:
        try:
            return await asyncio.open_unix_connection(str(path))
        except OSError as exc:
            last_error = exc
            if asyncio.get_running_loop().time() >= deadline:
                raise ControlUnavailableError(
                    f"Prompta scheduler is running but its control socket is unavailable: {path}"
                ) from last_error
            await asyncio.sleep(0.1)
