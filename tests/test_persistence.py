from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, cast

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
    assert jobs["leftovers"].source_revision == ""
    assert is_sqlite_file(path)


def test_existing_jobs_sqlite_adds_source_revision_column_in_place(tmp_path: Path) -> None:
    path = tmp_path / "jobs.sqlite3"
    with sqlite3.connect(path) as connection:
        connection.execute(
            """
            CREATE TABLE scheduled_jobs (
                name TEXT PRIMARY KEY,
                prompt TEXT NOT NULL,
                interval_seconds REAL NOT NULL,
                daily_at TEXT,
                exact_interval INTEGER NOT NULL DEFAULT 0,
                run_at_epoch REAL
            )
            """
        )
        connection.execute(
            "INSERT INTO scheduled_jobs VALUES (?, ?, ?, ?, ?, ?)",
            ("older", "Check an older report", 1800.0, None, 1, None),
        )

    jobs = load_jobs(path)

    assert jobs["older"].source_revision == ""
    with sqlite3.connect(path) as connection:
        columns = {row[1] for row in connection.execute("PRAGMA table_info(scheduled_jobs)")}
    assert "source_revision" in columns


def test_job_creation_revision_is_persisted_and_not_rewritten_on_edit(
    tmp_path: Path, monkeypatch
) -> None:
    path = tmp_path / "jobs.sqlite3"
    monkeypatch.setattr(jobs_module, "current_source_revision", lambda: "a" * 40)
    jobs_module.add_job(path, "bug", "Investigate the bug", 1800)

    monkeypatch.setattr(jobs_module, "current_source_revision", lambda: "b" * 40)
    jobs_module.add_job(path, "bug", "Investigate the bug carefully", 1800)

    job = load_jobs(path)["bug"]
    assert job.prompt == "Investigate the bug carefully"
    assert job.source_revision == "a" * 40


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


def test_scheduler_runtime_creates_job_status_index(tmp_path: Path) -> None:
    path = tmp_path / "runtime.sqlite3"
    SchedulerRuntime(path, path)
    with sqlite3.connect(path) as connection:
        indexes = {
            row[1] for row in connection.execute("PRAGMA index_list(delivery_intents)").fetchall()
        }

    assert "delivery_intents_job_status" in indexes


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

    record = store.records["client-a"]
    assert record["conversation_id"] == "chat-a"
    image = record["images"][0]
    stored_path = directory / image["path"]
    assert stored_path.name == "shot.png"
    assert len(stored_path.parent.name) == 64
    assert stored_path.read_bytes() == b"preview"
    assert not (directory / preview_id).exists()
    assert store.image_preview(preview_id) == (b"preview", "image/png")
    assert is_sqlite_file(store.path)
    assert not legacy.exists()


def test_image_preview_store_creates_created_at_index(tmp_path: Path) -> None:
    store = ImagePreviewStore(tmp_path)
    with sqlite3.connect(store.path) as connection:
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(image_preview_records)").fetchall()
        }

    assert "image_preview_records_created_idx" in indexes


def test_image_preview_sqlite_migrates_flat_file_and_adds_relative_path(tmp_path: Path) -> None:
    directory = tmp_path / "ui-image-previews"
    directory.mkdir()
    preview_id = "b" * 32
    (directory / preview_id).write_bytes(b"old-flat-preview")

    database = tmp_path / "ui-image-previews.sqlite3"
    connection = sqlite3.connect(database)
    connection.executescript(
        """
        CREATE TABLE image_preview_records (
            client_id TEXT PRIMARY KEY,
            conversation_id TEXT NOT NULL DEFAULT '',
            message TEXT NOT NULL DEFAULT '',
            created_at REAL NOT NULL
        );
        CREATE TABLE image_preview_images (
            client_id TEXT NOT NULL,
            position INTEGER NOT NULL,
            preview_id TEXT NOT NULL,
            name TEXT NOT NULL,
            media_type TEXT NOT NULL,
            PRIMARY KEY (client_id, position),
            UNIQUE (preview_id)
        );
        INSERT INTO image_preview_records(
            client_id, conversation_id, message, created_at
        ) VALUES ('client-old', 'chat-old', 'Old preview', 1.0);
        INSERT INTO image_preview_images(
            client_id, position, preview_id, name, media_type
        ) VALUES ('client-old', 0, 'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb', 'original name.png', 'image/png');
        """
    )
    connection.commit()
    connection.close()

    store = ImagePreviewStore(tmp_path)

    image = store.records["client-old"]["images"][0]
    stored_path = directory / image["path"]
    assert stored_path.name == "original name.png"
    assert len(stored_path.parent.name) == 64
    assert stored_path.read_bytes() == b"old-flat-preview"
    assert not (directory / preview_id).exists()

    connection = sqlite3.connect(database)
    row = connection.execute(
        "SELECT relative_path FROM image_preview_images WHERE preview_id = ?",
        (preview_id,),
    ).fetchone()
    connection.close()
    assert row is not None
    assert row[0] == image["path"]


def test_image_preview_binding_is_visible_across_store_instances(tmp_path: Path) -> None:
    writer = ImagePreviewStore(tmp_path)
    reader = ImagePreviewStore(tmp_path)
    preview_id = "c" * 32
    preview_dir = tmp_path / "ui-image-previews" / ("d" * 64)
    preview_dir.mkdir(parents=True)
    preview_path = preview_dir / "shot.png"
    preview_path.write_bytes(b"preview")

    writer.replace_staged(
        "client-cross-process",
        "Look",
        [
            {
                "id": preview_id,
                "name": "shot.png",
                "type": "image/png",
                "path": str(preview_path.relative_to(tmp_path / "ui-image-previews")),
            }
        ],
    )
    reader.bind("client-cross-process", "chat-cross-process", "Look")

    chat = {
        "messages": [
            {
                "role": "user",
                "content": "Look",
                "created_at": time.time(),
            }
        ]
    }
    writer.enrich(chat, "chat-cross-process")

    assert cast(Any, chat)["messages"][0]["attachments"][0]["id"] == preview_id


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
