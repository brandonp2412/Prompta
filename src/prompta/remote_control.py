from __future__ import annotations

import base64
import json
import shlex
import subprocess
import uuid
from pathlib import Path

_REMOTE_CONTROL_TIMEOUT_SECONDS = 11 * 60

def remote_control(
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
