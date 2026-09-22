from __future__ import annotations

import base64
import binascii
import re
import uuid
from pathlib import Path
from typing import Any

from .image_previews import ImagePreviewStore


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
        if not isinstance(raw_attachments, list) or len(raw_attachments) > 5:
            raise ValueError("Attachments must be a list of at most 5 files")

        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.image_previews.directory.mkdir(parents=True, exist_ok=True)
        saved: list[str] = []
        preview_files: list[Path] = []
        preview_images: list[dict[str, str]] = []
        total_bytes = 0
        try:
            for item in raw_attachments:
                if not isinstance(item, dict):
                    raise ValueError("Invalid attachment")
                name = Path(str(item.get("name") or "attachment")).name
                name = re.sub(r"[^A-Za-z0-9._ -]+", "_", name).strip(" .") or "attachment"
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
                target = self.upload_dir / f"{uuid.uuid4().hex}-{name}"
                target.write_bytes(content)
                target.chmod(0o600)
                saved.append(str(target))
                if client_id and media_type.startswith("image/"):
                    preview_id = uuid.uuid4().hex
                    preview_target = self.image_previews.directory / preview_id
                    preview_target.write_bytes(content)
                    preview_target.chmod(0o600)
                    preview_files.append(preview_target)
                    preview_images.append({"id": preview_id, "name": name, "type": media_type})
        except Exception:
            for target in saved:
                Path(target).unlink(missing_ok=True)
            for target in preview_files:
                target.unlink(missing_ok=True)
            raise
        if preview_images:
            self.image_previews.replace_staged(client_id, message, preview_images)
        return saved
