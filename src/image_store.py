from __future__ import annotations

import base64
import binascii
import hashlib
import os
import re
from pathlib import Path

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 8 * 1024 * 1024
MAX_VIDEO_BYTES = 50 * 1024 * 1024
_REF_RE = re.compile(r"^[0-9a-f]{64}/[A-Za-z0-9._-]{1,100}$")
_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
         ".gif": "image/gif", ".webp": "image/webp",
         ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm"}
_MP4_BRANDS = {
    b"isom", b"iso2", b"iso4", b"iso5", b"iso6", b"avc1",
    b"mp41", b"mp42", b"M4V ", b"MSNV", b"dash",
}


def image_refs(value: object) -> tuple[str, ...]:
    if not isinstance(value, (list, tuple)) or len(value) > MAX_IMAGES:
        raise ValueError("At most four attachments are supported")
    refs: list[str] = []
    for item in value:
        if not isinstance(item, str) or not _REF_RE.fullmatch(item):
            raise ValueError("Invalid attachment reference")
        refs.append(item)
    if len(set(refs)) != len(refs):
        raise ValueError("Duplicate attachment reference")
    return tuple(refs)


def image_mime(data: bytes) -> str:
    if len(data) >= 12 and data[4:8] == b"ftyp":
        brand = data[8:12]
        if brand == b"qt  ":
            return "video/quicktime"
        if brand in _MP4_BRANDS:
            return "video/mp4"
    if data.startswith(b"\x1a\x45\xdf\xa3") and b"webm" in data[:128]:
        return "video/webm"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return "image/webp"
    raise ValueError("Unsupported image or video format")


class ImageStore:
    def __init__(self, state_dir: Path) -> None:
        self.root = state_dir.expanduser() / "ui-uploads"

    def path(self, ref: str) -> Path:
        image_refs([ref])
        target = self.root / ref
        if not target.is_file():
            raise ValueError("Attachment no longer exists")
        return target

    def save(self, name: str, encoded: str) -> str:
        if not isinstance(name, str) or not isinstance(encoded, str):
            raise ValueError("Invalid attachment")
        if len(encoded) > ((MAX_VIDEO_BYTES + 2) // 3 * 4 + 4):
            raise ValueError("Attachment exceeds 50 MiB")
        try:
            data = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error) as exc:
            raise ValueError("Invalid attachment encoding") from exc
        if not data:
            raise ValueError("Attachment must not be empty")
        mime = image_mime(data)
        limit = MAX_VIDEO_BYTES if mime.startswith("video/") else MAX_IMAGE_BYTES
        if len(data) > limit:
            raise ValueError("Video exceeds 50 MiB" if mime.startswith("video/") else "Image exceeds 8 MiB")
        clean = re.sub(r"[^A-Za-z0-9._-]", "_", Path(name).name)[:100].strip("._")
        if not clean or _MIME.get(Path(clean).suffix.lower()) != mime:
            raise ValueError("Attachment extension does not match contents")
        ref = hashlib.sha256(data).hexdigest() + "/" + clean
        target = self.root / ref
        target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        target.parent.chmod(0o700)
        if not target.exists():
            try:
                descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            except FileExistsError:
                pass
            else:
                with os.fdopen(descriptor, "wb") as handle:
                    handle.write(data)
        return ref

    def read(self, ref: str) -> tuple[str, bytes]:
        path = self.path(ref)
        data = path.read_bytes()
        mime = image_mime(data)
        limit = MAX_VIDEO_BYTES if mime.startswith("video/") else MAX_IMAGE_BYTES
        if len(data) > limit or hashlib.sha256(data).hexdigest() != ref.split("/")[0]:
            raise ValueError("Stored attachment integrity check failed")
        if _MIME.get(path.suffix.lower()) != mime:
            raise ValueError("Stored attachment type mismatch")
        return mime, data
