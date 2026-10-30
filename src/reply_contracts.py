"""Durable, exact-branch manual reply contracts and irreversible dispatch leases."""

from __future__ import annotations

import hashlib
import os
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy import (
    Boolean,
    Column,
    Float,
    Index,
    MetaData,
    String,
    Table,
    Text,
    case,
    func,
    inspect,
    literal,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert

from .response_capture import CaptureResult
from .response_store import (
    ResponseStore,
    deserialize_tool_calls,
    history_recovery_attempts,
    local_chat_reads,
    merge_tool_calls,
    results,
)

ReplyStatus = Literal[
    "queued", "prepared", "preflight_failed", "dispatching", "outcome_unknown", "accepted",
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
    Column("tool_calls_json", Text, nullable=False, default="[]"),
    Column("message_id", String, nullable=False, default=""),
    Column("response_parent_id", String, nullable=False, default=""),
    Column("status", String, nullable=False),
    Column("queued_by_user", Boolean, nullable=False, server_default="0"),
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
                    *(Column(c.name, c.type, primary_key=c.primary_key, nullable=c.nullable,
                             server_default=c.server_default)
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
            existing_columns = {column["name"] for column in inspect(connection).get_columns(replies.name)}
            if "tool_calls_json" not in existing_columns:
                migration = Operations(MigrationContext.configure(connection))
                migration.add_column(replies.name, Column("tool_calls_json", Text, nullable=False, server_default="[]"))
            if "queued_by_user" not in existing_columns:
                migration = Operations(MigrationContext.configure(connection))
                migration.add_column(replies.name, Column("queued_by_user", Boolean, nullable=False, server_default="0"))
        self.responses._secure_files()

    @staticmethod
    def _public(row: dict[str, object]) -> dict[str, object]:
        public = {key: row[key] for key in (
            "reply_id", "send_id", "conversation_id", "parent_id", "message_id",
            "user_text", "assistant_text", "status", "queued_by_user", "created_at", "updated_at",
        )}
        public["tool_calls"] = deserialize_tool_calls(row["tool_calls_json"])
        return public

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
            if original is None or original["status"] not in ("completed", "interrupted", "unavailable"):
                raise ReplyConflict("A terminal, persisted Prompta run is required")
            conversation_id = str(original["conversation_id"])
            parent_id = str(original["message_id"])
            if not conversation_id or not parent_id:
                raise ReplyConflict("Original branch identity is incomplete")
            previous = connection.execute(select(replies).where(
                replies.c.send_id == send_id
            ).order_by(replies.c.created_at, replies.c.reply_id)).mappings().all()
            for turn in previous:
                if turn["status"] not in ("completed", "interrupted") or not turn["message_id"]:
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

    def queue_explicit_send(self, send_id: str, intent: ReplyIntent) -> dict[str, object]:
        """A user click durably authorizes one immutable send for the reply worker.

        Preparing an intent alone does not authorize dispatch. The worker sees
        only prepared rows explicitly opted in by this method. Ambiguous or
        already-claimed requests are never rearmed automatically.
        """
        turn = self.prepare(send_id, intent)
        if turn["status"] == "preflight_failed":
            turn = self.retry_preflight(intent.reply_id)
        if turn["status"] == "prepared":
            with self.engine.begin() as connection:
                connection.execute(update(replies).where(
                    replies.c.reply_id == intent.reply_id,
                    replies.c.send_id == send_id,
                    replies.c.conversation_id == intent.conversation_id,
                    replies.c.parent_id == intent.parent_id,
                    replies.c.user_text == intent.text,
                    replies.c.status == "prepared",
                ).values(queued_by_user=True))
            saved = self.get(intent.reply_id)
            assert saved is not None
            return saved
        return turn

    def queue_followup(
        self, send_id: str, reply_id: str, text: str, *, now: float | None = None,
    ) -> dict[str, object]:
        """Persist a user-clicked follow-up before the preceding answer is available.

        Queueing never infers a ChatGPT parent or performs a browser send. The
        parent is bound transactionally only after the preceding turn resolves.
        """
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,200}", reply_id):
            raise ValueError("Invalid follow-up identifier")
        if not text.strip() or len(text) > 32000:
            raise ValueError("Invalid follow-up text")
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            existing = connection.execute(select(replies).where(
                replies.c.reply_id == reply_id,
            )).mappings().one_or_none()
            if existing is not None:
                if (existing["send_id"], existing["user_text"], existing["queued_by_user"]) != (
                    send_id, text, True,
                ):
                    raise ReplyConflict("Idempotency key already belongs to a different follow-up")
                return self._public(dict(existing))
            if connection.execute(select(results.c.send_id).where(
                results.c.send_id == send_id,
            )).scalar_one_or_none() is None:
                raise ReplyConflict("A saved Prompta chat is required")
            outstanding = connection.execute(select(func.count()).select_from(replies).where(
                replies.c.send_id == send_id,
                replies.c.status.in_(("queued", "prepared", "preflight_failed", "dispatching",
                                     "accepted", "generating", "outcome_unknown")),
            )).scalar_one()
            if outstanding >= 20:
                raise ReplyConflict("This chat already has 20 unresolved follow-ups")
            connection.execute(insert(replies).values(
                reply_id=reply_id, send_id=send_id,
                conversation_id="", parent_id="", user_text=text,
                assistant_text="", message_id="", status="queued",
                queued_by_user=True, lease_owner="", lease_deadline=0,
                created_at=at, updated_at=at,
            ))
        row = self.get(reply_id)
        assert row is not None
        return row

    def next_queued_intent(
        self, *, exclude: set[str] | None = None, now: float | None = None,
    ) -> tuple[str, ReplyIntent] | None:
        """Bind one explicitly queued turn only after verified, ordered predecessors."""
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            candidates = connection.execute(select(replies).where(
                replies.c.queued_by_user.is_(True),
                replies.c.status.in_(("queued", "prepared")),
            ).order_by(replies.c.created_at, replies.c.reply_id)).mappings().all()
            for row in candidates:
                reply_id = str(row["reply_id"])
                if exclude and reply_id in exclude:
                    continue
                send_id = str(row["send_id"])
                original = connection.execute(select(results).where(
                    results.c.send_id == send_id,
                )).mappings().one_or_none()
                if (original is None or original["status"] not in
                        ("completed", "interrupted", "unavailable") or
                        not original["conversation_id"] or not original["message_id"]):
                    continue
                conversation_id = str(original["conversation_id"])
                parent_id = str(original["message_id"])
                predecessors = connection.execute(select(replies).where(
                    replies.c.send_id == send_id,
                ).order_by(replies.c.created_at, replies.c.reply_id)).mappings().all()
                eligible = False
                for previous in predecessors:
                    if previous["reply_id"] == reply_id:
                        eligible = True
                        break
                    if (previous["status"] not in ("completed", "interrupted")
                            or not previous["message_id"]
                            or previous["conversation_id"] != conversation_id
                            or previous["parent_id"] != parent_id):
                        break
                    parent_id = str(previous["message_id"])
                if not eligible:
                    continue
                if row["status"] == "queued":
                    connection.execute(update(replies).where(
                        replies.c.reply_id == reply_id, replies.c.status == "queued",
                    ).values(status="prepared", conversation_id=conversation_id,
                             parent_id=parent_id, updated_at=at))
                elif (row["conversation_id"], row["parent_id"]) != (
                    conversation_id, parent_id,
                ):
                    continue
                return send_id, ReplyIntent(
                    reply_id, conversation_id, parent_id, str(row["user_text"]),
                )
        return None

    def mark_preflight_failed(self, reply_id: str, *, now: float | None = None) -> bool:
        """Only a never-claimed reply can fail safely before dispatch."""
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(replies)
                .where(
                    replies.c.reply_id == reply_id,
                    replies.c.status == "prepared",
                )
                .values(status="preflight_failed", updated_at=at)
            )
        return changed.rowcount == 1

    def retry_preflight(self, reply_id: str, *, now: float | None = None) -> dict[str, object]:
        """Rearm only after an explicit click with the same immutable intent."""
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            connection.execute(
                update(replies)
                .where(
                    replies.c.reply_id == reply_id,
                    replies.c.status == "preflight_failed",
                )
                .values(status="prepared", updated_at=at)
            )
            row = (
                connection.execute(
                    select(replies).where(
                        replies.c.reply_id == reply_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            raise ReplyConflict("The saved reply is unavailable")
        return self._public(dict(row))

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
                results.c.status.in_(("completed", "interrupted", "unavailable")),
                results.c.conversation_id == conversation_id,
                results.c.message_id == "",
                results.c.assistant_text == original_answer,
            ).values(message_id=message_id.lower()))
        return changed.rowcount == 1

    def recover_reply_parent(
        self, send_id: str, reply_id: str, conversation_id: str,
        previous_parent_id: str, user_text: str, assistant_text: str,
        message_id: str,
    ) -> bool:
        """Bind a missing manual reply tip proven in the exact owned conversation DOM."""
        uuid = r"[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}"
        if (
            re.fullmatch(uuid, conversation_id) is None
            or re.fullmatch(uuid, previous_parent_id) is None
            or re.fullmatch(uuid, message_id) is None
            or message_id.lower() == previous_parent_id.lower()
        ):
            return False
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            original = connection.execute(select(results.c.conversation_id).where(
                results.c.send_id == send_id,
                results.c.status.in_(("completed", "interrupted", "unavailable")),
            )).scalar_one_or_none()
            if original != conversation_id:
                return False
            rows = connection.execute(select(replies).where(
                replies.c.send_id == send_id
            ).order_by(replies.c.created_at, replies.c.reply_id)).mappings().all()
            if not rows or rows[-1]["reply_id"] != reply_id:
                return False
            row = rows[-1]
            if (
                row["conversation_id"] != conversation_id
                or row["parent_id"] != previous_parent_id
                or row["user_text"] != user_text
                or row["assistant_text"] != assistant_text
                or row["message_id"]
                or row["status"] not in ("completed", "interrupted", "outcome_unknown")
                or row["lease_owner"]
            ):
                return False
            expected_parent = (
                rows[-2]["message_id"] if len(rows) > 1
                else connection.execute(select(results.c.message_id).where(
                    results.c.send_id == send_id
                )).scalar_one()
            )
            if expected_parent != previous_parent_id:
                return False
            changed = connection.execute(update(replies).where(
                replies.c.reply_id == reply_id,
                replies.c.status.in_(("completed", "interrupted", "outcome_unknown")),
                replies.c.message_id == "",
                replies.c.lease_owner == "",
            ).values(message_id=message_id.lower(), status=case(
                (replies.c.status == "outcome_unknown", "interrupted"),
                else_=replies.c.status,
            ), updated_at=time.time()))
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

    def acknowledge_submission(
        self, reply_id: str, owner: str, *, conversation_id: str, parent_id: str,
        now: float | None = None,
    ) -> bool:
        """Persist verified POST/DOM acceptance before an assistant message exists.

        This transition distinguishes a submitted but unfinished reply from an
        unconfirmed irreversible send, without manufacturing a response ID.
        """
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            changed = connection.execute(update(replies).where(
                replies.c.reply_id == reply_id,
                replies.c.status == "dispatching",
                replies.c.lease_owner == owner,
                replies.c.lease_deadline > at,
                replies.c.conversation_id == conversation_id,
                replies.c.parent_id == parent_id,
            ).values(status="accepted", updated_at=at))
        return changed.rowcount == 1

    def accepted(
        self, reply_id: str, owner: str, *, conversation_id: str, parent_id: str,
        message_id: str, response_parent_id: str | None = None,
        now: float | None = None,
    ) -> bool:
        at = time.time() if now is None else now
        response_parent = parent_id if response_parent_id is None else response_parent_id
        if not message_id or message_id == parent_id or response_parent == message_id:
            return False
        with self.engine.begin() as connection:
            changed = connection.execute(update(replies).where(
                replies.c.reply_id == reply_id,
                replies.c.status.in_(("dispatching", "accepted")),
                replies.c.message_id == "",
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
            if row is None:
                return False
            expected_parent = str(row["response_parent_id"] or row["parent_id"])
            parent_matches = (
                capture.parent_id == expected_parent
                if capture.source == "sse"
                else capture.parent_id is None or capture.parent_id == expected_parent
            )
            if (
                (capture.conversation_id, capture.message_id)
                != (row["conversation_id"], row["message_id"])
                or not parent_matches
                or not capture.text
                or len(capture.text) < len(str(row["assistant_text"]))
            ):
                return False
            complete = capture.status == "complete"
            changed = connection.execute(update(replies).where(
                replies.c.reply_id == reply_id, replies.c.lease_owner == owner,
                replies.c.status.in_(("accepted", "generating")),
            ).values(status="completed" if complete else "generating",
                     assistant_text=capture.text[:2 * 1024 * 1024],
                      tool_calls_json=merge_tool_calls(row["tool_calls_json"], capture.tool_calls),
                      updated_at=at,
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

    def next_history_reply_recovery(self, *, now: float | None = None) -> dict[str, object] | None:
        """Only first explicit replies with a verified original parent are eligible."""
        at = time.time() if now is None else now
        attempts = history_recovery_attempts.alias("reply_recovery")
        joined = replies.join(results, replies.c.send_id == results.c.send_id).outerjoin(
            attempts, attempts.c.send_id == literal("reply:") + replies.c.reply_id,
        )
        with self.engine.connect() as connection:
            row = connection.execute(select(
                replies.c.reply_id, replies.c.conversation_id, replies.c.parent_id,
                replies.c.user_text, results.c.user_text.label("original_prompt"),
                func.coalesce(attempts.c.attempt_count, 0).label("attempt_count"),
            ).select_from(joined).where(
                replies.c.status.in_(("outcome_unknown", "interrupted")),
                replies.c.lease_owner == "",
                replies.c.conversation_id != "",
                replies.c.parent_id == results.c.message_id,
                replies.c.conversation_id == results.c.conversation_id,
                results.c.status == "completed",
                func.coalesce(attempts.c.next_attempt_at, 0) <= at,
            ).order_by(
                func.coalesce(attempts.c.next_attempt_at, 0), replies.c.created_at.desc(),
            ).limit(1)).mappings().one_or_none()
        return dict(row) if row is not None else None

    def recover_historical_reply(
        self, reply_id: str, capture: CaptureResult, *, now: float | None = None,
    ) -> bool:
        """Read-only recovery; no uncertain dispatch claim is ever retried."""
        at = time.time() if now is None else now
        if (
            not capture.conversation_id or not capture.parent_id
            or not (capture.text or capture.tool_calls)
            or (capture.text and capture.status not in ("partial", "complete"))
            or not (capture.message_id or capture.observer_id)
        ):
            return False
        with self.engine.begin() as connection:
            row = connection.execute(select(replies).where(
                replies.c.reply_id == reply_id,
                replies.c.status.in_(("outcome_unknown", "interrupted")),
                replies.c.lease_owner == "",
            )).mappings().one_or_none()
            if row is None or (
                row["conversation_id"] != capture.conversation_id
                or row["parent_id"] != capture.parent_id
                or (row["message_id"] and capture.message_id
                    and row["message_id"] != capture.message_id)
            ):
                return False
            original = connection.execute(select(results.c.status, results.c.message_id).where(
                results.c.send_id == row["send_id"],
                results.c.conversation_id == capture.conversation_id,
            )).mappings().one_or_none()
            if original is None or original["status"] != "completed" or original["message_id"] != row["parent_id"]:
                return False
            text = capture.text[:2 * 1024 * 1024]
            if len(text) < len(str(row["assistant_text"])):
                if not capture.tool_calls:
                    return False
                text = str(row["assistant_text"])
            complete = capture.status == "complete" and bool(text)
            changed = connection.execute(update(replies).where(
                replies.c.reply_id == reply_id,
                replies.c.status.in_(("outcome_unknown", "interrupted")),
                replies.c.lease_owner == "",
            ).values(
                assistant_text=text,
                tool_calls_json=merge_tool_calls(row["tool_calls_json"], capture.tool_calls),
                message_id=capture.message_id or row["message_id"],
                status="completed" if complete else row["status"], updated_at=at,
            ))
        return changed.rowcount == 1

    def annotate_response_markers(self, summaries: list[dict[str, object]]) -> None:
        """Annotate only saved completed answers, never job/capture metadata activity."""
        send_ids = [str(item["send_id"]) for item in summaries]
        if not send_ids:
            return
        markers: dict[str, tuple[str, float]] = {send_id: ("", 0.0) for send_id in send_ids}
        with self.engine.connect() as connection:
            originals = connection.execute(select(
                results.c.send_id, results.c.assistant_text, results.c.status,
                results.c.finished_at,
            ).where(results.c.send_id.in_(send_ids))).all()
            for send_id, answer, status, finished_at in originals:
                if status == "completed" and answer:
                    marker = hashlib.sha256(
                        f"initial\0{send_id}\0{answer}".encode()
                    ).hexdigest()
                    markers[str(send_id)] = (marker, float(finished_at))
            completed_replies = connection.execute(select(
                replies.c.send_id, replies.c.reply_id, replies.c.assistant_text,
                replies.c.updated_at,
            ).where(
                replies.c.send_id.in_(send_ids),
                replies.c.status == "completed", replies.c.assistant_text != "",
            ).order_by(replies.c.created_at, replies.c.reply_id)).all()
            for send_id, reply_id, answer, updated_at in completed_replies:
                marker = hashlib.sha256(
                    f"manual\0{reply_id}\0{answer}".encode()
                ).hexdigest()
                markers[str(send_id)] = (marker, float(updated_at))
        for item in summaries:
            revision, at = markers[str(item["send_id"])]
            item["last_reply_revision"] = revision
            item["last_reply_at"] = at

    def mark_all_local_read(self) -> int:
        """Read all currently completed local answers, including off-page runs.

        Take a single SQLite write snapshot so a concurrent new reply cannot be
        accidentally acknowledged without its exact completed revision.
        """
        at = time.time()
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            markers: dict[str, str] = {}
            originals = connection.execute(
                select(
                    results.c.send_id,
                    results.c.assistant_text,
                ).where(
                    results.c.status == "completed",
                    results.c.assistant_text != "",
                )
            ).all()
            for send_id, answer in originals:
                markers[str(send_id)] = hashlib.sha256(
                    f"initial\0{send_id}\0{answer}".encode()
                ).hexdigest()
            completed_replies = connection.execute(
                select(
                    replies.c.send_id,
                    replies.c.reply_id,
                    replies.c.assistant_text,
                )
                .where(
                    replies.c.status == "completed",
                    replies.c.assistant_text != "",
                )
                .order_by(
                    replies.c.created_at,
                    replies.c.reply_id,
                )
            ).all()
            for send_id, reply_id, answer in completed_replies:
                markers[str(send_id)] = hashlib.sha256(
                    f"manual\0{reply_id}\0{answer}".encode()
                ).hexdigest()
            existing = dict(
                connection.execute(
                    select(
                        local_chat_reads.c.send_id,
                        local_chat_reads.c.seen_revision,
                    )
                ).all()
            )
            changed = {
                send_id: revision
                for send_id, revision in markers.items()
                if existing.get(send_id) != revision
            }
            for send_id, revision in changed.items():
                connection.execute(
                    insert(local_chat_reads)
                    .values(
                        send_id=send_id,
                        seen_revision=revision,
                        read_at=at,
                    )
                    .on_conflict_do_update(
                        index_elements=["send_id"],
                        set_={"seen_revision": revision, "read_at": at},
                    )
                )
        return len(changed)

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
             "assistant_text": original["assistant_text"],
              "tool_calls": deserialize_tool_calls(original["tool_calls_json"]),
              "status": original["status"],
             "created_at": original["created_at"], "updated_at": original["updated_at"]},
            *(self._public(dict(row)) for row in rows),
        ]
