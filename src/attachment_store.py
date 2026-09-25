from __future__ import annotations

import base64
import binascii
import uuid
from pathlib import Path
from typing import Any

from .file_storage import remove_stored_file, safe_basename, store_hashed_file
from .image_previews import ImagePreviewStore


def decode_attachments(raw_attachments: Any) -> list[tuple[str, str, bytes]]:
    if raw_attachments is None:
        return []
    if not isinstance(raw_attachments, list) or len(raw_attachments) > 5:
        raise ValueError("Attachments must be a list of at most 5 files")

    decoded: list[tuple[str, str, bytes]] = []
    total_bytes = 0
    for item in raw_attachments:
        if not isinstance(item, dict):
            raise ValueError("Invalid attachment")
        name = safe_basename(item.get("name"))
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
        decoded.append((name, media_type, content))
    return decoded


class AttachmentStore:
    def __init__(self, state_dir: Path, image_previews: ImagePreviewStore) -> None:
        self.upload_dir = state_dir / "ui-uploads"
        self.image_previews = image_previews

    def save(
        self,
        raw_attachments: Any,
        *,
        client_id: str = "",
        message: str = "",
    ) -> list[str]:
        if raw_attachments is None:
            return []
        attachments = decode_attachments(raw_attachments)

        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.image_previews.directory.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        preview_files: list[Path] = []
        preview_images: list[dict[str, str]] = []
        try:
            for name, media_type, content in attachments:
                target, _upload_path = store_hashed_file(self.upload_dir, name, content)
                saved.append(str(target))
                if client_id and media_type.startswith("image/"):
                    preview_id = uuid.uuid4().hex
                    preview_target, preview_path = store_hashed_file(
                        self.image_previews.directory,
                        name,
                        content,
                    )
                    preview_files.append(preview_target)
                    preview_images.append(
                        {
                            "id": preview_id,
                            "name": name,
                            "type": media_type,
                            "path": preview_path,
                        }
                    )
        except Exception:
            for target in saved:
                remove_stored_file(self.upload_dir, Path(target))
            for target in preview_files:
                remove_stored_file(self.image_previews.directory, target)
            raise
        if preview_images:
            self.image_previews.replace_staged(client_id, message, preview_images)
        return saved
