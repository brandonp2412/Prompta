"""Private, run-keyed results from Prompta-owned fresh ChatGPT tabs only."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Literal, TypedDict

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
    create_engine,
    delete,
    func,
    inspect,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import Engine

from .response_capture import CaptureResult, conversation_id_from_path

ResultStatus = Literal["queued", "accepted", "generating", "completed", "interrupted", "unavailable"]


class ResultsPage(TypedDict):
    items: list[dict[str, object]]
    total: int
    limit: int
    offset: int


_MAX_TEXT = 2 * 1024 * 1024
_SCHEMA = MetaData()
results = Table(
    "job_responses", _SCHEMA,
    Column("send_id", String, primary_key=True),
    Column("job_name", String, nullable=False, default=""),
    Column("user_text", Text, nullable=False),
    Column("assistant_text", Text, nullable=False, default=""),
    Column("tool_calls_json", Text, nullable=False, default="[]"),
    Column("status", String, nullable=False, default="queued"),
    Column("source", String, nullable=False, default=""),
    Column("conversation_id", String, nullable=False, default=""),
    Column("message_id", String, nullable=False, default=""),
    Column("parent_id", String, nullable=False, default=""),
    Column("created_at", Float, nullable=False),
    Column("accepted_at", Float, nullable=False, default=0),
    Column("updated_at", Float, nullable=False),
    Column("finished_at", Float, nullable=False, default=0),
    Column("capture_owner", String, nullable=False, default=""),
    Column("capture_deadline", Float, nullable=False, default=0),
)
Index("job_responses_active", results.c.status, results.c.capture_deadline)
local_chat_pins = Table(
    "local_chat_pins", _SCHEMA,
    Column("send_id", String, primary_key=True),
    Column("pinned_at", Float, nullable=False),
)


def serialize_tool_calls(calls: tuple[dict[str, object], ...]) -> str:
    """Persist bounded display data only; never source SSE frames or thoughts."""
    selected: list[dict[str, object]] = []
    for call in calls[:128]:
        candidate = json.dumps([*selected, call], ensure_ascii=False)
        if len(candidate) > 512_000:
            break
        selected.append(call)
    return json.dumps(selected, ensure_ascii=False)


def deserialize_tool_calls(value: object) -> list[dict[str, object]]:
    if not isinstance(value, str):
        return []
    try:
        parsed: object = json.loads(value)
    except (TypeError, ValueError):
        return []
    if not isinstance(parsed, list):
        return []
    return [{key: child for key, child in item.items() if isinstance(key, str)}
            for item in parsed[:128] if isinstance(item, dict)]


def merge_tool_calls(previous: object, incoming: tuple[dict[str, object], ...]) -> str:
    """Merge successive owned SSE snapshots by invocation ID without dropping earlier calls."""
    if not incoming:
        return previous if isinstance(previous, str) else "[]"
    merged = deserialize_tool_calls(previous)
    by_id = {str(call.get("id")): i for i, call in enumerate(merged)}
    for call in incoming:
        identifier = str(call.get("id"))
        if identifier in by_id:
            index = by_id[identifier]
            old = merged[index]
            refreshed = {**old, **call}
            for field in ("arguments", "result", "error"):
                if not call.get(field):
                    refreshed[field] = old.get(field, "")
            if old.get("status") in ("completed", "error") and call.get("status") == "running":
                refreshed["status"] = old["status"]
            merged[index] = refreshed
        elif len(merged) < 128:
            by_id[identifier] = len(merged)
            merged.append(call)
    return serialize_tool_calls(tuple(merged))


def _alive(owner: str) -> bool:
    pid, _, _token = owner.partition(":")
    try:
        number = int(pid)
        if number <= 0:
            return False
        os.kill(number, 0)
    except (ValueError, ProcessLookupError):
        return False
    except PermissionError:
        return True
    return True


class ResponseStore:
    """SQLAlchemy WAL store; Alembic upgrades only local schema, never ChatGPT."""

    def __init__(self, path: Path) -> None:
        self.path = path.expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.path.parent.chmod(0o700)
        fd = os.open(self.path, os.O_CREAT | os.O_RDWR, 0o600)
        os.close(fd)
        self.path.chmod(0o600)
        self.engine: Engine = create_engine(
            f"sqlite:///{self.path.resolve()}",
            connect_args={"timeout": 30.0, "check_same_thread": False},
        )
        with self.engine.begin() as connection:
            connection.exec_driver_sql("PRAGMA journal_mode=WAL")
            connection.exec_driver_sql("BEGIN IMMEDIATE")  # serialize migrations across workers
            if not inspect(connection).has_table(results.name):
                migration = Operations(MigrationContext.configure(connection))
                migration.create_table(
                    results.name,
                    *(Column(column.name, column.type, primary_key=column.primary_key,
                              nullable=column.nullable) for column in results.columns),
                )
                migration.create_index("job_responses_active", results.name, ["status", "capture_deadline"])
            if "tool_calls_json" not in {column["name"] for column in inspect(connection).get_columns(results.name)}:
                migration = Operations(MigrationContext.configure(connection))
                migration.add_column(results.name, Column("tool_calls_json", Text, nullable=False, server_default="[]"))
            if not inspect(connection).has_table(local_chat_pins.name):
                migration = Operations(MigrationContext.configure(connection))
                migration.create_table(
                    local_chat_pins.name,
                    Column("send_id", String, primary_key=True),
                    Column("pinned_at", Float, nullable=False),
                )
        self._secure_files()

    def _secure_files(self) -> None:
        for suffix in ("", "-wal", "-shm"):
            path = Path(str(self.path) + suffix)
            if path.exists():
                path.chmod(0o600)

    def ensure_queued(
        self, send_id: str, user_text: str, job_name: str = "", *, now: float | None = None
    ) -> None:
        at = time.time() if now is None else now
        statement = insert(results).values(
            send_id=send_id, job_name=job_name, user_text=user_text[:_MAX_TEXT],
            status="queued", created_at=at, updated_at=at,
        )
        with self.engine.begin() as connection:
            connection.execute(statement.on_conflict_do_nothing(index_elements=[results.c.send_id]))
            if job_name:
                connection.execute(update(results).where(
                    results.c.send_id == send_id, results.c.job_name == ""
                ).values(job_name=job_name))
        self._secure_files()

    def accept(self, send_id: str, owner: str, *, deadline: float, now: float | None = None) -> bool:
        at = time.time() if now is None else now
        if deadline <= at:
            return False
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(results).where(
                    results.c.send_id == send_id,
                    results.c.status.in_(("queued", "unavailable")),
                ).values(status="accepted", accepted_at=at, updated_at=at,
                         capture_owner=owner, capture_deadline=deadline)
            )
        return changed.rowcount == 1

    def bind_conversation_route(
        self, send_id: str, owner: str, path: object, *, now: float | None = None
    ) -> bool:
        """Persist only a verified fresh route while its unique capture lease is live."""
        conversation_id = conversation_id_from_path(path)
        if conversation_id is None:
            return False
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            changed = connection.execute(update(results).where(
                results.c.send_id == send_id,
                results.c.capture_owner == owner,
                results.c.status.in_(("accepted", "generating")),
                results.c.capture_deadline > at,
                or_(results.c.conversation_id == "", results.c.conversation_id == conversation_id),
            ).values(conversation_id=conversation_id, updated_at=at))
        return changed.rowcount == 1

    def write(
        self, send_id: str, owner: str, capture: CaptureResult, *, now: float | None = None
    ) -> bool:
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            row = connection.execute(
                select(results).where(
                    results.c.send_id == send_id,
                    results.c.capture_owner == owner,
                    results.c.status.in_(("accepted", "generating")),
                    results.c.capture_deadline > at,
                )
            ).mappings().one_or_none()
            if row is None:
                return False
            for name, candidate in (
                ("message_id", capture.message_id),
                ("conversation_id", capture.conversation_id),
                ("parent_id", capture.parent_id),
            ):
                if row[name] and candidate and row[name] != candidate:
                    # A branch changed. Never join text from different answers.
                    return False
            text = capture.text[:_MAX_TEXT]
            complete = capture.status == "complete" and bool(
                text and (capture.message_id or capture.observer_id)
            )
            prior = str(row["assistant_text"])
            tool_json = merge_tool_calls(row["tool_calls_json"], capture.tool_calls)
            if not text:
                if tool_json == row["tool_calls_json"]:
                    return True
                changed = connection.execute(update(results).where(
                    results.c.send_id == send_id,
                    results.c.capture_owner == owner,
                    results.c.status.in_(("accepted", "generating")),
                    results.c.capture_deadline > at,
                ).values(tool_calls_json=tool_json, updated_at=at))
                return changed.rowcount == 1
            # A shorter partial observer snapshot cannot erase a longer answer.
            if not complete and len(text) < len(prior):
                text = prior
            if (
                not complete
                and row["status"] == "generating"
                and text == prior
                and tool_json == row["tool_calls_json"]
                and row["source"] == capture.source
                and (not capture.conversation_id or row["conversation_id"] == capture.conversation_id)
                and (not capture.message_id or row["message_id"] == capture.message_id)
                and (not capture.parent_id or row["parent_id"] == capture.parent_id)
            ):
                # Mutation observers may repeat a snapshot. Avoid a WAL write every five seconds.
                return True
            changed = connection.execute(
                update(results).where(
                    results.c.send_id == send_id,
                    results.c.capture_owner == owner,
                    results.c.status.in_(("accepted", "generating")),
                    results.c.capture_deadline > at,
                ).values(
                    assistant_text=text,
                    tool_calls_json=tool_json,
                    status="completed" if complete else "generating",
                    source=capture.source if complete or len(text) >= len(prior) else row["source"],
                    conversation_id=capture.conversation_id or row["conversation_id"],
                    message_id=capture.message_id or row["message_id"],
                    parent_id=capture.parent_id or row["parent_id"],
                    updated_at=at,
                    finished_at=at if complete else 0,
                    capture_owner="" if complete else owner,
                )
            )
            return changed.rowcount == 1

    def renew_capture_deadline(
        self, send_id: str, owner: str, *, deadline: float, now: float | None = None,
    ) -> bool:
        """Extend only a live, uniquely held capture lease after verified activity."""
        at = time.time() if now is None else now
        if deadline <= at:
            return False
        with self.engine.begin() as connection:
            changed = connection.execute(update(results).where(
                results.c.send_id == send_id,
                results.c.capture_owner == owner,
                results.c.status.in_(("accepted", "generating")),
                results.c.capture_deadline > at,
                results.c.capture_deadline < deadline,
            ).values(capture_deadline=deadline))
        return changed.rowcount == 1

    def finish(
        self, send_id: str, owner: str, status: Literal["interrupted", "unavailable"],
        *, now: float | None = None,
    ) -> bool:
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            changed = connection.execute(
                update(results).where(
                    results.c.send_id == send_id,
                    results.c.capture_owner == owner,
                    results.c.status.in_(("accepted", "generating")),
                ).values(status=status, updated_at=at, finished_at=at, capture_owner="")
            )
        return changed.rowcount == 1

    def unavailable(self, send_id: str, *, now: float | None = None) -> None:
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            connection.execute(update(results).where(
                results.c.send_id == send_id, results.c.status == "queued"
            ).values(status="unavailable", updated_at=at, finished_at=at))

    def recover_orphans(self, *, now: float | None = None) -> int:
        at = time.time() if now is None else now
        with self.engine.begin() as connection:
            rows = connection.execute(select(results.c.send_id, results.c.capture_owner,
                results.c.capture_deadline).where(results.c.status.in_(("accepted", "generating")))).all()
            recovered = 0
            for send_id, owner, deadline in rows:
                if deadline > at and _alive(str(owner)):
                    continue
                changed = connection.execute(update(results).where(
                    results.c.send_id == send_id,
                    results.c.capture_owner == owner,
                    results.c.status.in_(("accepted", "generating")),
                ).values(status="interrupted", updated_at=at, finished_at=at, capture_owner=""))
                recovered += changed.rowcount
        return recovered

    def active_capture_send_ids(
        self, job_prefixes: tuple[str, ...] | None = None, *, now: float
    ) -> set[str]:
        """Count only live owned captures; never read private response bodies."""
        if job_prefixes == ():
            return set()
        predicates = [results.c.job_name != ""]
        if job_prefixes is not None:
            predicates.append(
                or_(*(results.c.job_name.startswith(prefix) for prefix in job_prefixes))
            )
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(results.c.send_id).where(
                    results.c.status.in_(("accepted", "generating")),
                    results.c.capture_deadline > now,
                    results.c.capture_owner != "",
                    *predicates,
                )
            ).scalars().all()
        return {str(send_id) for send_id in rows}

    def set_local_pin(self, send_id: str, *, pinned: bool) -> bool:
        """Pin a known local run only; never request or alter ChatGPT pin state."""
        if not send_id or len(send_id) > 200 or "/" in send_id:
            raise ValueError("Invalid local run ID")
        with self.engine.begin() as connection:
            exists = connection.execute(
                select(results.c.send_id).where(results.c.send_id == send_id)
            ).scalar_one_or_none()
            if exists is None:
                return False
            if pinned:
                connection.execute(
                    insert(local_chat_pins).values(send_id=send_id, pinned_at=time.time())
                    .on_conflict_do_nothing(index_elements=["send_id"])
                )
            else:
                connection.execute(delete(local_chat_pins).where(local_chat_pins.c.send_id == send_id))
        return True

    def import_legacy_local_pins(self, send_ids: list[str]) -> None:
        """One-time migration from a browser's old pins, without resurrecting old pins later."""
        if len(send_ids) > 24 or any(
            not send_id or len(send_id) > 200 or "/" in send_id for send_id in send_ids
        ):
            raise ValueError("Invalid legacy local pin IDs")
        with self.engine.begin() as connection:
            connection.exec_driver_sql("BEGIN IMMEDIATE")
            if connection.execute(select(func.count()).select_from(local_chat_pins)).scalar_one():
                return
            pinned_at = time.time()
            for index, send_id in enumerate(dict.fromkeys(send_ids)):
                exists = connection.execute(
                    select(results.c.send_id).where(results.c.send_id == send_id)
                ).scalar_one_or_none()
                if exists is not None:
                    connection.execute(insert(local_chat_pins).values(
                        send_id=send_id, pinned_at=pinned_at - index * 0.001,
                    ))

    def local_pinned_runs(self) -> list[dict[str, object]]:
        """Compact local-only sidebar summaries, including runs outside the visible page."""
        with self.engine.connect() as connection:
            rows = connection.execute(
                select(
                    results.c.send_id, results.c.job_name,
                    func.substr(results.c.user_text, 1, 180).label("user_preview"),
                    func.substr(results.c.assistant_text, 1, 180).label("assistant_preview"),
                    results.c.status, results.c.created_at, results.c.updated_at,
                    results.c.finished_at,
                )
                .select_from(local_chat_pins.join(
                    results, local_chat_pins.c.send_id == results.c.send_id
                ))
                .order_by(local_chat_pins.c.pinned_at.desc(), local_chat_pins.c.send_id.desc())
            ).mappings().all()
        items: list[dict[str, object]] = []
        for row in rows:
            prompt = str(row["user_preview"])
            answer = str(row["assistant_preview"])
            title = str(row["job_name"]) or (prompt.splitlines()[0][:100] if prompt else "")
            items.append({
                "send_id": row["send_id"], "job_name": row["job_name"], "title": title,
                "status": row["status"], "preview": (answer or prompt)[:180],
                "has_response": bool(answer), "created_at": row["created_at"],
                "updated_at": row["updated_at"], "finished_at": row["finished_at"],
            })
        return items

    def get(self, send_id: str) -> dict[str, object] | None:
        with self.engine.connect() as connection:
            row = connection.execute(select(results).where(results.c.send_id == send_id)).mappings().one_or_none()
        return dict(row) if row is not None else None

    def records(self, *, limit: int = 100) -> list[dict[str, object]]:
        with self.engine.connect() as connection:
            rows = connection.execute(select(results).order_by(results.c.created_at.desc()).limit(
                max(1, min(1000, limit)))).mappings().all()
        return [dict(row) for row in rows]

    def page(
        self, *, limit: int = 20, offset: int = 0, query: str = "", status: str = ""
    ) -> ResultsPage:
        """List only locally persisted Prompta runs; never touch browser state."""
        if status and status not in (
            "queued", "accepted", "generating", "completed", "interrupted", "unavailable"
        ):
            raise ValueError("Invalid result status")
        if len(query) > 200 or not 1 <= limit <= 50 or not 0 <= offset <= 100_000:
            raise ValueError("Invalid results pagination or search")
        criteria = []
        if status:
            criteria.append(results.c.status == status)
        if query:
            escaped = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            pattern = f"%{escaped}%"
            criteria.append(or_(
                results.c.job_name.ilike(pattern, escape="\\"),
                results.c.user_text.ilike(pattern, escape="\\"),
                results.c.assistant_text.ilike(pattern, escape="\\"),
            ))
        with self.engine.connect() as connection:
            count = connection.execute(select(func.count()).select_from(results).where(*criteria)).scalar_one()
            rows = connection.execute(
                select(results.c.send_id, results.c.job_name,
                       func.substr(results.c.user_text, 1, 180).label("user_preview"),
                       func.substr(results.c.assistant_text, 1, 180).label("assistant_preview"),
                       results.c.status, results.c.created_at, results.c.updated_at,
                       results.c.finished_at)
                .where(*criteria).order_by(results.c.created_at.desc(), results.c.send_id.desc())
                .limit(limit).offset(offset)
            ).mappings().all()
        items: list[dict[str, object]] = []
        for row in rows:
            prompt = str(row["user_preview"])
            answer = str(row["assistant_preview"])
            title = str(row["job_name"]) or (prompt.splitlines()[0][:100] if prompt else "")
            items.append({
                "send_id": row["send_id"], "job_name": row["job_name"], "title": title,
                "status": row["status"], "preview": (answer or prompt)[:180],
                "has_response": bool(answer), "created_at": row["created_at"],
                "updated_at": row["updated_at"], "finished_at": row["finished_at"],
            })
        return {"items": items, "total": count, "limit": limit, "offset": offset}

    def detail(self, send_id: str) -> dict[str, object] | None:
        if not send_id or len(send_id) > 200:
            return None
        row = self.get(send_id)
        if row is None:
            return None
        detail = {key: row[key] for key in (
            "send_id", "job_name", "user_text", "assistant_text", "status", "source",
            "created_at", "accepted_at", "updated_at", "finished_at",
        )}
        detail["tool_calls"] = deserialize_tool_calls(row["tool_calls_json"])
        return detail
