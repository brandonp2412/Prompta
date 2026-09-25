from __future__ import annotations

import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any

from .file_storage import remove_stored_file, resolve_stored_file, safe_basename, store_hashed_file
from .persistence import connect_sqlite, read_legacy_json, remove_legacy_json


def preview_attachment_assignments(
    messages: list[object],
    records: list[dict[str, Any]],
    conversation_id: str,
) -> list[tuple[int, list[dict[str, str]]]]:
    matching_records = [
        dict(record)
        for record in records
        if str(record.get("conversation_id") or "") == conversation_id
    ]
    matching_records.sort(key=lambda record: float(record.get("created_at") or 0.0))

    assignments: list[tuple[int, list[dict[str, str]]]] = []
    used_indexes: set[int] = set()
    for record in matching_records:
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
        index, _message = min(
            candidates,
            key=lambda item: abs(float(item[1].get("created_at") or 0.0) - record_created),
        )
        used_indexes.add(index)

        images = record.get("images")
        if not isinstance(images, list):
            continue
        attachments = [
            {
                "id": str(image.get("id") or ""),
                "name": str(image.get("name") or "image"),
                "type": str(image.get("type") or "image/*"),
            }
            for image in images
            if isinstance(image, dict) and image.get("id")
        ]
        assignments.append((index, attachments))
    return assignments


class ImagePreviewStore:
    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "ui-image-previews.sqlite3"
        self.legacy_path = state_dir / "ui-image-previews.json"
        self.directory = state_dir / "ui-image-previews"
        self.lock = threading.Lock()
        self._initialize()
        self.records = self._load_database()
        self._migrate_legacy()
        self.records = self.load()

    def _connect(self) -> sqlite3.Connection:
        return connect_sqlite(self.path)

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS image_preview_records (
                    client_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL DEFAULT '',
                    message TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS image_preview_images (
                    client_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    preview_id TEXT NOT NULL,
                    name TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    relative_path TEXT NOT NULL DEFAULT '',
                    PRIMARY KEY (client_id, position),
                    UNIQUE (preview_id),
                    FOREIGN KEY (client_id)
                        REFERENCES image_preview_records(client_id)
                        ON DELETE CASCADE
                );

                CREATE INDEX IF NOT EXISTS image_preview_records_created_idx
                    ON image_preview_records(created_at, client_id);
                """
            )
            connection.execute("PRAGMA foreign_keys=ON")
            columns = {
                str(row["name"])
                for row in connection.execute("PRAGMA table_info(image_preview_images)")
            }
            if "relative_path" not in columns:
                connection.execute(
                    "ALTER TABLE image_preview_images "
                    "ADD COLUMN relative_path TEXT NOT NULL DEFAULT ''"
                )

    def _load_database(self) -> dict[str, dict[str, Any]]:
        with self._connect() as connection:
            records = connection.execute(
                """
                SELECT client_id, conversation_id, message, created_at
                FROM image_preview_records
                ORDER BY created_at, client_id
                """
            ).fetchall()
            images = connection.execute(
                """
                SELECT client_id, position, preview_id, name, media_type, relative_path
                FROM image_preview_images
                ORDER BY client_id, position
                """
            ).fetchall()

        by_client: dict[str, list[dict[str, str]]] = {}
        for row in images:
            by_client.setdefault(str(row["client_id"]), []).append(
                {
                    "id": str(row["preview_id"]),
                    "name": str(row["name"]),
                    "type": str(row["media_type"]),
                    "path": str(row["relative_path"] or ""),
                }
            )
        return {
            str(row["client_id"]): {
                "client_id": str(row["client_id"]),
                "conversation_id": str(row["conversation_id"] or ""),
                "message": str(row["message"] or ""),
                "created_at": float(row["created_at"] or 0.0),
                "images": by_client.get(str(row["client_id"]), []),
            }
            for row in records
        }

    def _migrate_legacy(self) -> None:
        payload = read_legacy_json(self.legacy_path)
        if payload is None:
            return
        if not self.records and isinstance(payload, dict):
            raw_records = payload.get("records")
            if isinstance(raw_records, dict):
                self.records = {
                    str(client_id): dict(record)
                    for client_id, record in raw_records.items()
                    if isinstance(record, dict)
                }
                self._write_locked()
        remove_legacy_json(self.legacy_path)

    def _file_for_image(self, image: dict[str, Any]) -> Path | None:
        stored = resolve_stored_file(self.directory, image.get("path"))
        if stored is not None:
            return stored
        preview_id = str(image.get("id") or "")
        if not preview_id:
            return None
        legacy = self.directory / preview_id
        return legacy if legacy.is_file() else None

    def _migrate_flat_preview(self, image: dict[str, Any], legacy: Path) -> Path:
        preview_id = str(image.get("id") or "")
        content = legacy.read_bytes()
        target, relative_path = store_hashed_file(
            self.directory,
            safe_basename(image.get("name"), default="image"),
            content,
            seed=preview_id.encode("utf-8"),
        )
        if target != legacy:
            legacy.unlink(missing_ok=True)
        image["path"] = relative_path
        return target

    def load(self) -> dict[str, dict[str, Any]]:
        records = self._load_database()
        cutoff = time.time() - (30 * 24 * 60 * 60)
        cleaned: dict[str, dict[str, Any]] = {}
        changed = False
        for client_id, raw_record in records.items():
            try:
                created_at = float(raw_record.get("created_at") or 0.0)
            except (TypeError, ValueError):
                created_at = 0.0
            conversation_id = str(raw_record.get("conversation_id") or "")
            if not conversation_id and created_at and created_at < cutoff:
                changed = True
                continue
            images = raw_record.get("images")
            if not isinstance(images, list):
                changed = True
                continue
            kept_images: list[dict[str, str]] = []
            for image in images:
                if not isinstance(image, dict):
                    changed = True
                    continue
                preview_id = str(image.get("id") or "")
                if not preview_id:
                    changed = True
                    continue

                stored = resolve_stored_file(self.directory, image.get("path"))
                if stored is None:
                    legacy = self.directory / preview_id
                    if not legacy.is_file():
                        changed = True
                        continue
                    try:
                        stored = self._migrate_flat_preview(image, legacy)
                    except OSError:
                        changed = True
                        continue
                    changed = True
                if not stored.is_file():
                    changed = True
                    continue

                kept_images.append(
                    {
                        "id": preview_id,
                        "name": safe_basename(image.get("name"), default="image"),
                        "type": str(image.get("type") or "image/*"),
                        "path": str(image.get("path") or ""),
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
            else:
                changed = True
        if changed:
            self.records = cleaned
            self._write_locked()
        return cleaned

    def _write_locked(self) -> None:
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute("DELETE FROM image_preview_images")
            connection.execute("DELETE FROM image_preview_records")
            for client_id, record in self.records.items():
                connection.execute(
                    """
                    INSERT INTO image_preview_records(
                        client_id, conversation_id, message, created_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (
                        client_id,
                        str(record.get("conversation_id") or ""),
                        str(record.get("message") or ""),
                        float(record.get("created_at") or time.time()),
                    ),
                )
                images = record.get("images")
                if not isinstance(images, list):
                    continue
                connection.executemany(
                    """
                    INSERT INTO image_preview_images(
                        client_id, position, preview_id, name, media_type, relative_path
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            client_id,
                            position,
                            str(image.get("id") or ""),
                            safe_basename(image.get("name"), default="image"),
                            str(image.get("type") or "image/*"),
                            str(image.get("path") or ""),
                        )
                        for position, image in enumerate(images)
                        if isinstance(image, dict) and image.get("id")
                    ],
                )

    def _write_record_locked(self, client_id: str) -> None:
        record = self.records.get(client_id)
        if not isinstance(record, dict):
            return
        images = record.get("images")
        with self._connect() as connection:
            connection.execute("PRAGMA foreign_keys=ON")
            connection.execute(
                "DELETE FROM image_preview_images WHERE client_id = ?",
                (client_id,),
            )
            connection.execute(
                "DELETE FROM image_preview_records WHERE client_id = ?",
                (client_id,),
            )
            connection.execute(
                """
                INSERT INTO image_preview_records(
                    client_id, conversation_id, message, created_at
                ) VALUES (?, ?, ?, ?)
                """,
                (
                    client_id,
                    str(record.get("conversation_id") or ""),
                    str(record.get("message") or ""),
                    float(record.get("created_at") or time.time()),
                ),
            )
            if isinstance(images, list):
                connection.executemany(
                    """
                    INSERT INTO image_preview_images(
                        client_id, position, preview_id, name, media_type, relative_path
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            client_id,
                            position,
                            str(image.get("id") or ""),
                            safe_basename(image.get("name"), default="image"),
                            str(image.get("type") or "image/*"),
                            str(image.get("path") or ""),
                        )
                        for position, image in enumerate(images)
                        if isinstance(image, dict) and image.get("id")
                    ],
                )

    def replace_staged(
        self,
        client_id: str,
        message: str,
        images: list[dict[str, str]],
    ) -> None:
        if not client_id or not images:
            return
        with self.lock:
            self.records = self._load_database()
            previous = self.records.get(client_id)
            if isinstance(previous, dict) and not previous.get("conversation_id"):
                for image in previous.get("images", []):
                    if not isinstance(image, dict):
                        continue
                    target = self._file_for_image(image)
                    if target is None:
                        continue
                    try:
                        remove_stored_file(self.directory, target)
                    except OSError:
                        pass
            self.records[client_id] = {
                "client_id": client_id,
                "conversation_id": "",
                "message": message,
                "created_at": time.time(),
                "images": images,
            }
            self._write_record_locked(client_id)

    def bind(self, client_id: str, conversation_id: str, message: str) -> None:
        if not client_id or not conversation_id:
            return
        with self.lock:
            with self._connect() as connection:
                if message:
                    connection.execute(
                        """
                        UPDATE image_preview_records
                        SET conversation_id = ?, message = ?
                        WHERE client_id = ?
                        """,
                        (conversation_id, message, client_id),
                    )
                else:
                    connection.execute(
                        """
                        UPDATE image_preview_records
                        SET conversation_id = ?
                        WHERE client_id = ?
                        """,
                        (conversation_id, client_id),
                    )
            self.records = self._load_database()

    def enrich(self, chat: dict[str, Any], conversation_id: str) -> None:
        messages = chat.get("messages")
        if not isinstance(messages, list):
            return
        with self.lock:
            self.records = self._load_database()
            records = [dict(record) for record in self.records.values() if isinstance(record, dict)]
        for index, attachments in preview_attachment_assignments(
            messages,
            records,
            conversation_id,
        ):
            message = messages[index]
            if isinstance(message, dict):
                message["attachments"] = attachments

    def image_preview(self, preview_id: str) -> tuple[bytes, str] | None:
        if not re.fullmatch(r"[a-f0-9]{32}", preview_id):
            return None
        media_type = "application/octet-stream"
        target: Path | None = None
        with self.lock:
            self.records = self._load_database()
            for record in self.records.values():
                if not isinstance(record, dict):
                    continue
                for image in record.get("images", []):
                    if not isinstance(image, dict) or str(image.get("id") or "") != preview_id:
                        continue
                    media_type = str(image.get("type") or "application/octet-stream")
                    target = self._file_for_image(image)
                    break
                if target is not None:
                    break
        if target is None:
            return None
        try:
            body = target.read_bytes()
        except OSError:
            return None
        return body, media_type
