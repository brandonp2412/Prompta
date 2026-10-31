from __future__ import annotations

import hashlib
import time

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert
from sqlalchemy.engine import Engine

from .reply_tables import replies
from .response_tables import local_chat_reads, results


def _answer_revision(kind: str, identity: str, text: str) -> str:
    payload = f"{kind}\0{identity}\0{text}".encode()
    return hashlib.sha256(payload).hexdigest()


class ReplyReadState:
    engine: Engine

    def annotate_response_markers(self, summaries: list[dict[str, object]]) -> None:
        """Annotate only saved completed answers, never job/capture metadata activity."""
        send_ids = [str(item["send_id"]) for item in summaries]
        if not send_ids:
            return
        markers: dict[str, tuple[str, float]] = {send_id: ("", 0.0) for send_id in send_ids}
        with self.engine.connect() as connection:
            originals = connection.execute(
                select(
                    results.c.send_id,
                    results.c.assistant_text,
                    results.c.status,
                    results.c.finished_at,
                ).where(results.c.send_id.in_(send_ids))
            ).all()
            for send_id, answer, status, finished_at in originals:
                if status == "completed" and answer:
                    marker = _answer_revision("initial", str(send_id), str(answer))
                    markers[str(send_id)] = (marker, float(finished_at))
            completed = connection.execute(
                select(
                    replies.c.send_id,
                    replies.c.reply_id,
                    replies.c.assistant_text,
                    replies.c.updated_at,
                )
                .where(
                    replies.c.send_id.in_(send_ids),
                    replies.c.status == "completed",
                    replies.c.assistant_text != "",
                )
                .order_by(replies.c.created_at, replies.c.reply_id)
            ).all()
            for send_id, reply_id, answer, updated_at in completed:
                marker = _answer_revision("manual", str(reply_id), str(answer))
                markers[str(send_id)] = (marker, float(updated_at))
            attention_ids = set(
                connection.execute(
                    select(replies.c.send_id)
                    .where(
                        replies.c.send_id.in_(send_ids),
                        replies.c.status.in_(
                            (
                                "preflight_failed",
                                "outcome_unknown",
                                "interrupted",
                                "unavailable",
                            )
                        ),
                    )
                    .distinct()
                ).scalars()
            )
        for item in summaries:
            send_id = str(item["send_id"])
            revision, at = markers[send_id]
            item["last_reply_revision"] = revision
            item["last_reply_at"] = at
            item["needs_attention"] = (
                item["status"] in ("interrupted", "unavailable") or send_id in attention_ids
            )

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
                markers[str(send_id)] = _answer_revision("initial", str(send_id), str(answer))
            completed = connection.execute(
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
            for send_id, reply_id, answer in completed:
                markers[str(send_id)] = _answer_revision("manual", str(reply_id), str(answer))
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
