"""Durable, exact-branch manual reply contracts and irreversible dispatch leases."""

from __future__ import annotations

import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Column,
    Float,
    Index,
    MetaData,
    String,
    Table,
    Text,
    case,
    inspect,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert

from .response_capture import CaptureResult
from .response_store import ResponseStore, results

ReplyStatus = Literal[
    "prepared", "dispatching", "outcome_unknown", "accepted",
    "generating", "completed", "interrupted",
]
_SCHEMA = MetaData()
replies = Table(
    "manual_reply_turns", _SCHEMA,
    Column("reply_id", String, primary_key=True),
    Column("send_id", String, nullable=False),
    Column("conversation_id", String, nullable=False),
    Column("parent_id", String, nullable=False),
    Column("user_text", Text, nullable=False),
    Column("assistant_text", Text, nullable=False, default=""),
    Column("message_id", String, nullable=False, default=""),
    Column("response_parent_id", String, nullable=False, default=""),
    Column("status", String, nullable=False),
    Column("lease_owner", String, nullable=False, default=""),
    Column("lease_deadline", Float, nullable=False, default=0),
    Column("created_at", Float, nullable=False),
    Column("updated_at", Float, nullable=False),
)
Index("manual_reply_turns_branch", replies.c.send_id, replies.c.created_at)


@dataclass(frozen=True)
class ReplyIntent:
    reply_id: str
    conversation_id: str
    parent_id: str
    text: str

    @classmethod
    def parse(cls, payload: dict[str, object]) -> ReplyIntent:
        if set(payload) != {"reply_id", "conversation_id", "parent_id", "text"}:
            raise ValueError("Invalid reply fields")
        values = [payload[name] for name in ("reply_id", "conversation_id", "parent_id")]
        if not all(
            isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9_-]{16,200}", value)
            for value in values
        ):
            raise ValueError("Invalid reply/branch identifier")
        text = payload["text"]
        if not isinstance(text, str) or not text.strip() or len(text) > 32000:
            raise ValueError("Invalid reply text")
        reply_id, conversation_id, parent_id = values
        assert isinstance(reply_id, str)
        assert isinstance(conversation_id, str)
        assert isinstance(parent_id, str)
        return cls(reply_id, conversation_id, parent_id, text)


class ReplyConflict(ValueError):
    """An intent is stale, ambiguous or reuses an idempotency key."""


class ManualReplyStore:
    """The caller must explicitly claim a prepared intent before attempting any send."""

    def __init__(self, path: Path) -> None:
        self.responses = ResponseStore(path)
        self.engine = self.responses.engine
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            if not inspect(connection).has_table(replies.name):
                migration = Operations(MigrationContext.configure(connection))
                migration.create_table(
                    replies.name,
                    *(Column(c.name, c.type, primary_key=c.primary_key, nullable=c.nullable)
                      for c in replies.columns),
                )
                migration.create_index(
                    "manual_reply_turns_branch", replies.name, ["send_id", "created_at"]
                )
            elif not any(
                column["name"] == "response_parent_id"
                for column in inspect(connection).get_columns(replies.name)
            ):
                migration = Operations(MigrationContext.configure(connection))
                migration.add_column(
                    replies.name, Column(
                        "response_parent_id", String, nullable=False, server_default="",
                    ),
                )
        self.responses._secure_files()

    @staticmethod
    def _public(row: dict[str, object]) -> dict[str, object]:
        return {key: row[key] for key in (
            "reply_id", "send_id", "conversation_id", "parent_id", "message_id",
            "user_text", "assistant_text", "status", "created_at", "updated_at",
        )}

    def get(self, reply_id: str) -> dict[str, object] | None:
        with self.engine.connect() as connection:
            row = connection.execute(select(replies).where(
                replies.c.reply_id == reply_id,
            )).mappings().one_or_none()
        return self._public(dict(row)) if row is not None else None

    def prepare(self, send_id: str, intent: ReplyIntent, *, now: float | None = None) -> dict[str, object]:
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            existing = connection.execute(select(replies).where(
                replies.c.reply_id == intent.reply_id
            )).mappings().one_or_none()
            if existing is not None:
                if (existing["send_id"], existing["conversation_id"], existing["parent_id"],
                        existing["user_text"]) != (
                    send_id, intent.conversation_id, intent.parent_id, intent.text,
                ):
                    raise ReplyConflict("Idempotency key already belongs to a different reply")
                return self._public(dict(existing))
            original = connection.execute(select(results).where(
                results.c.send_id == send_id
            )).mappings().one_or_none()
            if original is None or original["status"] != "completed":
                raise ReplyConflict("A completed, persisted Prompta run is required")
            conversation_id = str(original["conversation_id"])
            parent_id = str(original["message_id"])
            if not conversation_id or not parent_id:
                raise ReplyConflict("Original branch identity is incomplete")
            previous = connection.execute(select(replies).where(
                replies.c.send_id == send_id
            ).order_by(replies.c.created_at, replies.c.reply_id)).mappings().all()
            for turn in previous:
                if turn["status"] != "completed" or not turn["message_id"]:
                    raise ReplyConflict("An unresolved reply already occupies this branch")
                if turn["conversation_id"] != conversation_id or turn["parent_id"] != parent_id:
                    raise ReplyConflict("Persisted branch lineage is inconsistent")
                parent_id = str(turn["message_id"])
            if (intent.conversation_id, intent.parent_id) != (conversation_id, parent_id):
                raise ReplyConflict("The reply targets a stale or different ChatGPT branch")
            connection.execute(insert(replies).values(
                reply_id=intent.reply_id, send_id=send_id,
                conversation_id=conversation_id, parent_id=parent_id,
                user_text=intent.text, assistant_text="", message_id="",
                status="prepared", lease_owner="", lease_deadline=0,
                created_at=at, updated_at=at,
            ))
        return {
            "reply_id": intent.reply_id, "send_id": send_id,
            "conversation_id": conversation_id, "parent_id": parent_id,
            "message_id": "", "user_text": intent.text, "assistant_text": "",
            "status": "prepared", "created_at": at, "updated_at": at,
        }

    def recover_original_parent(
        self, send_id: str, conversation_id: str, message_id: str, original_answer: str
    ) -> bool:
        """Bind one missing parent only after an explicit, exact-branch DOM verification."""
        uuid = r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"
        if re.fullmatch(uuid, conversation_id) is None or re.fullmatch(uuid, message_id) is None:
            return False
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            existing = connection.execute(select(replies.c.reply_id).where(
                replies.c.send_id == send_id
            ).limit(1)).first()
            if existing is not None:
                return False
            changed = connection.execute(update(results).where(
                results.c.send_id == send_id,
                results.c.status == "completed",
                results.c.conversation_id == conversation_id,
                results.c.message_id == "",
                results.c.assistant_text == original_answer,
            ).values(message_id=message_id.lower()))
        return changed.rowcount == 1

    def claim(self, reply_id: str, owner: str, *, deadline: float, now: float | None = None) -> bool:
        """A single irreversible dispatch claim; recovery never retries it."""
        at = time.time() if now is None else now
        if not owner or deadline <= at:
            return False
        with self.engine.begin() as connection:
            changed = connection.execute(update(replies).where(
                replies.c.reply_id == reply_id, replies.c.status == "prepared"
            ).values(status="dispatching", lease_owner=owner,
                     lease_deadline=deadline, updated_at=at))
        return changed.rowcount == 1

    def accepted(
        self, reply_id: str, owner: str, *, conversation_id: str, parent_id: str,
        message_id: str, response_parent_id: str | None = None,
        now: float | None = None,
    ) -> bool:
        at = time.time() if now is None else now
        response_parent = response_parent_id or parent_id
        if not message_id or message_id == parent_id or response_parent == message_id:
            return False
        with self.engine.begin() as connection:
            changed = connection.execute(update(replies).where(
                replies.c.reply_id == reply_id, replies.c.status == "dispatching",
                replies.c.lease_owner == owner, replies.c.lease_deadline > at,
                replies.c.conversation_id == conversation_id, replies.c.parent_id == parent_id,
            ).values(status="accepted", message_id=message_id,
                     response_parent_id=response_parent, updated_at=at))
        return changed.rowcount == 1

    def observe(self, reply_id: str, owner: str, capture: CaptureResult,
                *, now: float | None = None) -> bool:
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            row = connection.execute(select(replies).where(
                replies.c.reply_id == reply_id, replies.c.lease_owner == owner,
                replies.c.status.in_(("accepted", "generating")),
                replies.c.lease_deadline > at,
            )).mappings().one_or_none()
            if row is None or (capture.conversation_id, capture.message_id, capture.parent_id) != (
                row["conversation_id"], row["message_id"],
                row["response_parent_id"] or row["parent_id"],
            ) or not capture.text or len(capture.text) < len(str(row["assistant_text"])):
                return False
            complete = capture.status == "complete"
            changed = connection.execute(update(replies).where(
                replies.c.reply_id == reply_id, replies.c.lease_owner == owner,
                replies.c.status.in_(("accepted", "generating")),
            ).values(status="completed" if complete else "generating",
                     assistant_text=capture.text[:2 * 1024 * 1024], updated_at=at,
                     lease_owner="" if complete else owner))
        return changed.rowcount == 1

    def renew(
        self, reply_id: str, owner: str, *, deadline: float, now: float | None = None,
    ) -> bool:
        at = time.time() if now is None else now
        if deadline <= at:
            return False
        with self.engine.begin() as connection:
            changed = connection.execute(update(replies).where(
                replies.c.reply_id == reply_id, replies.c.lease_owner == owner,
                replies.c.status.in_(("dispatching", "accepted", "generating")),
                replies.c.lease_deadline > at,
            ).values(lease_deadline=deadline, updated_at=at))
        return changed.rowcount == 1

    def finish(
        self, reply_id: str, owner: str, *, uncertain: bool = False,
        now: float | None = None,
    ) -> bool:
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            changed = connection.execute(update(replies).where(
                replies.c.reply_id == reply_id, replies.c.lease_owner == owner,
                replies.c.status.in_(("dispatching", "accepted", "generating")),
            ).values(
                status=case(
                    (replies.c.status == "dispatching", "outcome_unknown"),
                    else_="interrupted",
                ) if uncertain else "interrupted",
                lease_owner="", updated_at=at,
            ))
        return changed.rowcount == 1

    def recover_orphans(self, *, now: float | None = None) -> int:
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            changed = 0
            rows = connection.execute(select(
                replies.c.reply_id, replies.c.status, replies.c.lease_owner,
                replies.c.lease_deadline,
            ).where(replies.c.status.in_(("dispatching", "accepted", "generating")))).all()
            for reply_id, status, owner, deadline in rows:
                try:
                    os.kill(int(str(owner).split(":", 1)[0]), 0)
                    alive = True
                except (ValueError, ProcessLookupError):
                    alive = False
                except PermissionError:
                    alive = True
                if deadline > at and alive:
                    continue
                result = connection.execute(update(replies).where(
                    replies.c.reply_id == reply_id, replies.c.status == status,
                    replies.c.lease_owner == owner,
                ).values(status="outcome_unknown" if status == "dispatching" else "interrupted",
                         lease_owner="", updated_at=at))
                changed += result.rowcount
        return changed

    def turns(self, send_id: str) -> list[dict[str, object]] | None:
        original = self.responses.get(send_id)
        if original is None:
            return None
        with self.engine.connect() as connection:
            rows = connection.execute(select(replies).where(
                replies.c.send_id == send_id
            ).order_by(replies.c.created_at, replies.c.reply_id)).mappings().all()
        return [
            {"reply_id": "", "send_id": send_id,
             "conversation_id": original["conversation_id"], "parent_id": original["parent_id"],
             "message_id": original["message_id"], "user_text": original["user_text"],
             "assistant_text": original["assistant_text"], "status": original["status"],
             "created_at": original["created_at"], "updated_at": original["updated_at"]},
            *(self._public(dict(row)) for row in rows),
        ]
