from __future__ import annotations

import json
from pathlib import Path

import prompta.jobs as jobs_module
import prompta.scheduler_runtime as scheduler_module
from prompta.image_previews import ImagePreviewStore
from prompta.jobs import load_jobs
from prompta.persistence import is_sqlite_file
from prompta.pinned_chats import PinnedChatStore
from prompta.scheduler_runtime import SchedulerRuntime


def test_legacy_jobs_json_is_imported_into_sqlite_in_place(tmp_path: Path) -> None:
    path = tmp_path / "jobs.json"
    path.write_text(
        json.dumps(
            {
                "jobs": {
                    "leftovers": {
                        "prompt": "Audit unchecked transcripts",
                        "interval_seconds": 5400,
                        "exact_interval": True,
                    }
                }
            }
        )
    )

    jobs = load_jobs(path)

    assert jobs["leftovers"].prompt == "Audit unchecked transcripts"
    assert jobs["leftovers"].interval_seconds == 5400
    assert jobs["leftovers"].exact_interval is True
    assert is_sqlite_file(path)


def test_legacy_scheduler_state_json_is_imported_into_sqlite_in_place(tmp_path: Path) -> None:
    state_path = tmp_path / "state.json"
    jobs_path = tmp_path / "runtime.sqlite3"
    state_path.write_text(
        json.dumps(
            {
                "scheduler": {"last_attempt_at": 123.0},
                "jobs": {"leftovers": {"paused": True, "next_due_at_epoch": 456.0}},
            }
        )
    )

    runtime = SchedulerRuntime(state_path, jobs_path)

    assert runtime.scheduler_state()["last_attempt_at"] == 123.0
    assert runtime.job_state("leftovers") == {
        "paused": True,
        "next_due_at_epoch": 456.0,
    }
    assert is_sqlite_file(state_path)


def test_legacy_pins_json_is_imported_then_removed(tmp_path: Path) -> None:
    legacy = tmp_path / "ui-pinned-chats.json"
    legacy.write_text(json.dumps({"ids": ["chat-a", "chat-b"]}))

    store = PinnedChatStore(tmp_path)

    assert store.snapshot() == {"initialized": True, "ids": ["chat-a", "chat-b"]}
    assert store.path.name == "ui-pinned-chats.sqlite3"
    assert is_sqlite_file(store.path)
    assert not legacy.exists()


def test_legacy_image_preview_json_is_imported_then_removed(tmp_path: Path) -> None:
    directory = tmp_path / "ui-image-previews"
    directory.mkdir()
    preview_id = "a" * 32
    (directory / preview_id).write_bytes(b"preview")
    legacy = tmp_path / "ui-image-previews.json"
    legacy.write_text(
        json.dumps(
            {
                "records": {
                    "client-a": {
                        "client_id": "client-a",
                        "conversation_id": "chat-a",
                        "message": "Look at this",
                        "created_at": 1.0,
                        "images": [{"id": preview_id, "name": "shot.png", "type": "image/png"}],
                    }
                }
            }
        )
    )

    store = ImagePreviewStore(tmp_path)

    assert store.records["client-a"]["conversation_id"] == "chat-a"
    assert store.image_preview(preview_id) == (b"preview", "image/png")
    assert is_sqlite_file(store.path)
    assert not legacy.exists()


def test_runtime_database_imports_separate_legacy_job_and_state_files(
    tmp_path: Path, monkeypatch
) -> None:
    runtime_path = tmp_path / "state" / "runtime.sqlite3"
    legacy_jobs = tmp_path / "config" / "jobs.json"
    legacy_state = tmp_path / "state" / "state.json"
    legacy_jobs.parent.mkdir(parents=True)
    legacy_state.parent.mkdir(parents=True)
    legacy_jobs.write_text(
        json.dumps(
            {
                "jobs": {
                    "leftovers": {
                        "prompt": "Audit unchecked transcripts",
                        "interval_seconds": 5400,
                    }
                }
            }
        )
    )
    legacy_state.write_text(
        json.dumps({"jobs": {"leftovers": {"status": "healthy", "paused": False}}})
    )

    monkeypatch.setattr(jobs_module, "DEFAULT_RUNTIME_PATH", runtime_path)
    monkeypatch.setattr(jobs_module, "LEGACY_JOBS_PATH", legacy_jobs)
    monkeypatch.setattr(scheduler_module, "DEFAULT_RUNTIME_PATH", runtime_path)
    monkeypatch.setattr(scheduler_module, "LEGACY_STATE_PATH", legacy_state)

    runtime = SchedulerRuntime(runtime_path, runtime_path)
    jobs = load_jobs(runtime_path)

    assert jobs["leftovers"].prompt == "Audit unchecked transcripts"
    assert runtime.job_state("leftovers") == {"status": "healthy", "paused": False}
    assert is_sqlite_file(runtime_path)
    assert not legacy_jobs.exists()
    assert not legacy_state.exists()
