from __future__ import annotations

import json
import subprocess
from http import HTTPStatus
from pathlib import Path
from threading import Thread
from unittest.mock import MagicMock, patch
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import pytest

from prompta.pinned_chats import PinnedChatStore
from prompta.read_state import ConversationReadState
from prompta.web import PromptaUIServer, ReadOnlyChatStore
from prompta.web_jobs import WebJobService


def _post_json(url: str, payload: dict[str, object]) -> tuple[int, dict[str, object]]:
    request = Request(
        url,
        data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urlopen(request, timeout=2) as response:
        return response.status, json.loads(response.read())


def test_schedule_http_routes_preserve_validation_and_serialization(tmp_path: Path) -> None:
    server = PromptaUIServer(
        ("127.0.0.1", 0),
        ReadOnlyChatStore(tmp_path / "missing.sqlite3"),
        tmp_path / "state.json",
        jobs_path=tmp_path / "jobs.json",
    )
    server.job_service.schedule_at = MagicMock(
        return_value={
            "name": "at-4000000000-deadbeef00",
            "prompt": "do work",
            "run_at_epoch": 4_000_000_000.0,
            "source_revision": "rev",
            "scheduler_started": True,
            "server": "glass",
        }
    )
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base_url = f"http://127.0.0.1:{server.server_port}"
    try:
        status, payload = _post_json(
            f"{base_url}/api/schedule-at",
            {"prompt": "  do work  ", "run_at_epoch": "4000000000"},
        )
        assert status == HTTPStatus.CREATED
        assert payload == {
            "ok": True,
            "name": "at-4000000000-deadbeef00",
            "prompt": "do work",
            "run_at_epoch": 4_000_000_000.0,
            "source_revision": "rev",
            "scheduler_started": True,
            "server": "glass",
        }
        server.job_service.schedule_at.assert_called_once_with("do work", 4_000_000_000.0)

        request = Request(
            f"{base_url}/api/schedule",
            data=json.dumps({"prompt": "do work", "interval_minutes": "not-a-number"}).encode(),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with pytest.raises(HTTPError) as error:
            urlopen(request, timeout=2)
        assert error.value.code == HTTPStatus.BAD_REQUEST
        assert json.loads(error.value.read()) == {
            "error": "Schedule interval must be a finite value greater than zero"
        }
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_pinned_chat_promote_existing_destination_contract(tmp_path: Path) -> None:
    store = PinnedChatStore(tmp_path)
    store.seed(["first", "second", "third"])

    assert store.promote("first", "second") == {
        "initialized": True,
        "ids": ["second", "third"],
    }
    assert PinnedChatStore(tmp_path).snapshot() == {
        "initialized": True,
        "ids": ["second", "third"],
    }


def test_read_state_decorate_handles_invalid_assistant_timestamp(tmp_path: Path) -> None:
    state = ConversationReadState(tmp_path, clock=lambda: 100.0)

    source = {"id": "chat", "last_assistant_at": "not-a-time", "title": "Chat"}
    assert state.decorate([source]) == [
        {"id": "chat", "last_assistant_at": "not-a-time", "title": "Chat", "unread": False}
    ]
    assert source == {"id": "chat", "last_assistant_at": "not-a-time", "title": "Chat"}


def test_job_cli_daily_add_command_does_not_require_interval(tmp_path: Path) -> None:
    start_scheduler = MagicMock(return_value=True)
    service = WebJobService(
        tmp_path / "jobs.json",
        tmp_path / "state.json",
        "glass",
        start_scheduler,
    )
    completed = subprocess.CompletedProcess(args=[], returncode=0, stdout="", stderr="")
    with (
        patch("prompta.web_jobs.subprocess.run", return_value=completed) as run_cli,
        patch.object(service, "scheduled_jobs", return_value={"jobs": [], "server": "glass"}),
    ):
        result = service.run_cli(
            " ADD ",
            {
                "name": "daily",
                "prompt": "Do work",
                "daily_at": "09:30",
                "interval_minutes": True,
                "exact_interval": True,
            },
        )

    command = run_cli.call_args.args[0]
    assert command[3:] == [
        "add",
        "daily",
        "Do work",
        "--daily-at",
        "09:30",
        "--jobs-file",
        str(tmp_path / "jobs.json"),
    ]
    assert start_scheduler.call_count == 1
    assert result == {
        "ok": True,
        "command": ["prompta", *command[3:]],
        "jobs": [],
        "server": "glass",
    }
