from __future__ import annotations

import hashlib
import uuid
from pathlib import Path


def safe_basename(value: object, *, default: str = "attachment") -> str:
    candidate = str(value or default).replace("\\", "/")
    name = Path(candidate).name.replace("\x00", "").strip()
    return name if name not in {"", ".", ".."} else default


def storage_hash(content: bytes, *, seed: bytes | None = None) -> str:
    nonce = seed if seed is not None else uuid.uuid4().bytes
    return hashlib.sha256(nonce + content).hexdigest()


def store_hashed_file(
    root: Path,
    name: object,
    content: bytes,
    *,
    seed: bytes | None = None,
) -> tuple[Path, str]:
    filename = safe_basename(name)
    directory_name = storage_hash(content, seed=seed)
    directory = root / directory_name
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    target = directory / filename
    target.write_bytes(content)
    target.chmod(0o600)
    return target, f"{directory_name}/{filename}"


def resolve_stored_file(root: Path, relative_path: object) -> Path | None:
    raw = str(relative_path or "").strip()
    if not raw:
        return None
    relative = Path(raw)
    if relative.is_absolute() or ".." in relative.parts:
        return None
    candidate = root.joinpath(relative)
    try:
        candidate.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return None
    return candidate


def remove_stored_file(root: Path, target: Path) -> None:
    try:
        target.unlink(missing_ok=True)
    finally:
        parent = target.parent
        if parent != root:
            try:
                parent.rmdir()
            except OSError:
                pass
