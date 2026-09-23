from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any

from .metadata_store import (
    UI_METADATA_DB,
    import_recorded,
    metadata_connection,
    record_import,
)


class ImagePreviewStore:
    _LEGACY_IMPORT = "ui-image-previews-json"

    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / UI_METADATA_DB
        self.legacy_path = state_dir / "ui-image-previews.json"
        self.directory = state_dir / "ui-image-previews"
        self.lock = threading.Lock()
        self._migrate()
        self._import_legacy_json()
        self.records = self.load()

    def _migrate(self) -> None:
        with metadata_connection(self.path) as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS image_preview_records (
                    client_id TEXT PRIMARY KEY,
                    conversation_id TEXT NOT NULL DEFAULT '',
                    message TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );

                CREATE TABLE IF NOT EXISTS image_preview_files (
                    preview_id TEXT PRIMARY KEY,
                    client_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    media_type TEXT NOT NULL,
                    FOREIGN KEY(client_id)
                        REFERENCES image_preview_records(client_id)
                        ON DELETE CASCADE,
                    UNIQUE(client_id, position)
                );

                CREATE INDEX IF NOT EXISTS image_preview_files_client_idx
                    ON image_preview_files(client_id, position);
                """
            )

    def _clean_records(self, records: object) -> dict[str, dict[str, Any]]:
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
                file_path = self.directory / preview_id
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
                normalized_id = str(client_id)
                cleaned[normalized_id] = {
                    "client_id": normalized_id,
                    "conversation_id": conversation_id,
                    "message": str(raw_record.get("message") or ""),
                    "created_at": created_at or time.time(),
                    "images": kept_images,
                }
        return cleaned

    def _database_records(self) -> dict[str, dict[str, Any]]:
        with metadata_connection(self.path) as connection:
            rows = connection.execute(
                """
                SELECT client_id, conversation_id, message, created_at
                FROM image_preview_records
                ORDER BY created_at, client_id
                """
            ).fetchall()
            images = connection.execute(
                """
                SELECT preview_id, client_id, name, media_type
                FROM image_preview_files
                ORDER BY client_id, position
                """
            ).fetchall()

        records: dict[str, dict[str, Any]] = {
            str(row["client_id"]): {
                "client_id": str(row["client_id"]),
                "conversation_id": str(row["conversation_id"] or ""),
                "message": str(row["message"] or ""),
                "created_at": float(row["created_at"] or 0.0),
                "images": [],
            }
            for row in rows
        }
        for row in images:
            record = records.get(str(row["client_id"]))
            if record is None:
                continue
            record["images"].append(
                {
                    "id": str(row["preview_id"]),
                    "name": str(row["name"] or "image"),
                    "type": str(row["media_type"] or "image/*"),
                }
            )
        return records

    @staticmethod
    def _write_records(connection, records: dict[str, dict[str, Any]]) -> None:
        connection.execute("DELETE FROM image_preview_files")
        connection.execute("DELETE FROM image_preview_records")
        for client_id, record in records.items():
            connection.execute(
                """
                INSERT INTO image_preview_records(
                    client_id,
                    conversation_id,
                    message,
                    created_at
                )
                VALUES (?, ?, ?, ?)
                """,
                (
                    client_id,
                    str(record.get("conversation_id") or ""),
                    str(record.get("message") or ""),
                    float(record.get("created_at") or time.time()),
                ),
            )
            connection.executemany(
                """
                INSERT INTO image_preview_files(
                    preview_id,
                    client_id,
                    position,
                    name,
                    media_type
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (
                        str(image.get("id") or ""),
                        client_id,
                        position,
                        str(image.get("name") or "image"),
                        str(image.get("type") or "image/*"),
                    )
                    for position, image in enumerate(record.get("images", []))
                    if isinstance(image, dict) and image.get("id")
                ],
            )

    def _import_legacy_json(self) -> None:
        try:
            payload = json.loads(self.legacy_path.read_text(encoding="utf-8"))
        except (FileNotFoundError, OSError, ValueError):
            return
        if not isinstance(payload, dict):
            return

        records = self._clean_records(payload.get("records", {}))
        imported = False
        with metadata_connection(self.path) as connection:
            if not import_recorded(connection, self._LEGACY_IMPORT):
                existing = connection.execute(
                    "SELECT 1 FROM image_preview_records LIMIT 1"
                ).fetchone()
                if existing is None:
                    self._write_records(connection, records)
                record_import(connection, self._LEGACY_IMPORT)
            imported = import_recorded(connection, self._LEGACY_IMPORT)
        if imported:
            try:
                self.legacy_path.unlink(missing_ok=True)
            except OSError:
                pass

    def load(self) -> dict[str, dict[str, Any]]:
        records = self._database_records()
        cleaned = self._clean_records(records)
        if cleaned != records:
            with metadata_connection(self.path) as connection:
                self._write_records(connection, cleaned)
        return cleaned

    def _write_locked(self) -> None:
        with metadata_connection(self.path) as connection:
            self._write_records(connection, self.records)

    def replace_staged(
        self,
        client_id: str,
        message: str,
        images: list[dict[str, str]],
    ) -> None:
        if not client_id or not images:
            return
        with self.lock:
            previous = self.records.get(client_id)
            if isinstance(previous, dict) and not previous.get("conversation_id"):
                for image in previous.get("images", []):
                    if isinstance(image, dict):
                        try:
                            (self.directory / str(image.get("id") or "")).unlink(missing_ok=True)
                        except OSError:
                            pass
            self.records[client_id] = {
                "client_id": client_id,
                "conversation_id": "",
                "message": message,
                "created_at": time.time(),
                "images": images,
            }
            self._write_locked()

    def bind(self, client_id: str, conversation_id: str, message: str) -> None:
        with self.lock:
            record = self.records.get(client_id)
            if not isinstance(record, dict):
                return
            record["conversation_id"] = conversation_id
            if message:
                record["message"] = message
            self._write_locked()

    def enrich(self, chat: dict[str, Any], conversation_id: str) -> None:
        messages = chat.get("messages")
        if not isinstance(messages, list):
            return
        with self.lock:
            records = [
                dict(record)
                for record in self.records.values()
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
        with self.lock:
            for record in self.records.values():
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
            body = (self.directory / preview_id).read_bytes()
        except OSError:
            return None
        return body, media_type
