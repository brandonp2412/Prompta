from __future__ import annotations

import json
import threading
from collections.abc import Iterable
from pathlib import Path


class PinnedChatStore:
    """Persist UI pin state independently of any one browser profile."""

    _LIMIT = 500

    def __init__(self, state_dir: Path) -> None:
        self.path = state_dir / "ui-pinned-chats.json"
        self.lock = threading.Lock()
        self._initialized, self._ids = self._load()

    @classmethod
    def _normalize(cls, values: Iterable[object]) -> list[str]:
        ids: list[str] = []
        seen: set[str] = set()
        for value in values:
            chat_id = str(value or "").strip()
            if not chat_id or chat_id in seen:
                continue
            seen.add(chat_id)
            ids.append(chat_id)
            if len(ids) >= cls._LIMIT:
                break
        return ids

    def _load(self) -> tuple[bool, list[str]]:
        try:
            payload = json.loads(self.path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return False, []
        except (OSError, ValueError):
            return False, []

        if not isinstance(payload, dict):
            return False, []
        raw_ids = payload.get("ids")
        if not isinstance(raw_ids, list):
            return False, []
        return True, self._normalize(raw_ids)

    def _write_locked(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps({"ids": self._ids}, ensure_ascii=False),
            encoding="utf-8",
        )
        temporary.replace(self.path)

    def snapshot(self) -> dict[str, object]:
        with self.lock:
            return {"initialized": self._initialized, "ids": list(self._ids)}

    def seed(self, values: Iterable[object]) -> dict[str, object]:
        with self.lock:
            if not self._initialized:
                self._ids = self._normalize(values)
                self._initialized = True
                self._write_locked()
            return {"initialized": self._initialized, "ids": list(self._ids)}

    def set_pinned(self, chat_id: str, pinned: bool) -> dict[str, object]:
        normalized = str(chat_id or "").strip()
        if not normalized:
            raise ValueError("Chat id is required")

        with self.lock:
            changed = False
            if pinned:
                if normalized not in self._ids:
                    self._ids.append(normalized)
                    changed = True
            elif normalized in self._ids:
                self._ids.remove(normalized)
                changed = True

            if changed or not self._initialized:
                self._initialized = True
                self._write_locked()

            return {"initialized": self._initialized, "ids": list(self._ids)}

    def promote(self, previous_id: str, next_id: str) -> dict[str, object]:
        previous = str(previous_id or "").strip()
        next_value = str(next_id or "").strip()
        if not previous or not next_value:
            raise ValueError("Both previous and next chat ids are required")

        with self.lock:
            if previous in self._ids and previous != next_value:
                previous_index = self._ids.index(previous)
                self._ids.remove(previous)
                if next_value not in self._ids:
                    self._ids.insert(previous_index, next_value)
                self._initialized = True
                self._write_locked()

            return {"initialized": self._initialized, "ids": list(self._ids)}
