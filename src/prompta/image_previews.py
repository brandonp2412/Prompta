from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any


class ImagePreviewStore:
    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "ui-image-previews.json"
        self.directory = state_dir / "ui-image-previews"
        self.lock = threading.Lock()
        self.records = self.load()

    def load(self) -> dict[str, dict[str, Any]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
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
                cleaned[str(client_id)] = {
                    "client_id": str(client_id),
                    "conversation_id": conversation_id,
                    "message": str(raw_record.get("message") or ""),
                    "created_at": created_at or time.time(),
                    "images": kept_images,
                }
        return cleaned

    def _write_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"records": self.records}, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self.path)

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
