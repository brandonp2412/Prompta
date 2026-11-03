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


_LIVE_OBSERVATION_SECONDS = 15 * 60.0


def visible_reply_status(status: str, observed_at: float, *, now: float) -> str:
    """A detached capture is live only briefly after exact ChatGPT verification."""
    if (status in ("interrupted", "outcome_unknown", "unavailable") and observed_at > 0
            and observed_at <= now < observed_at + _LIVE_OBSERVATION_SECONDS):
        return "generating"
    return status


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
                    results.c.live_observed_at,
                ).where(results.c.send_id.in_(send_ids))
            ).all()
            original_live = {}
            for send_id, answer, status, finished_at, observed_at in originals:
                original_live[str(send_id)] = (str(status), float(observed_at))
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
            # The sidebar describes the latest user turn. Earlier capture failures
            # must not override a newer working or completed follow-up.
            latest_replies = {
                str(send_id): (str(status), float(observed_at), bool(queued_by_user))
                for send_id, status, observed_at, queued_by_user in connection.execute(
                    select(replies.c.send_id, replies.c.status, replies.c.live_observed_at,
                           replies.c.queued_by_user)
                    .where(replies.c.send_id.in_(send_ids), replies.c.status != "merged")
                    .order_by(replies.c.created_at, replies.c.reply_id)
                )
            }
        for item in summaries:
            send_id = str(item["send_id"])
            revision, at = markers[send_id]
            item["last_reply_revision"] = revision
            item["last_reply_at"] = at
            latest = latest_replies.get(send_id)
            if latest is not None:
                reply_status, observed_at, queued_by_user = latest
                status = visible_reply_status(reply_status, observed_at, now=time.time())
                # A user-queued follow-up is active chat work even before its worker
                # claims it. Keep its queued label, but distinguish it from an
                # unsent fresh chat in the sidebar's activity indicator.
                item["queued_followup"] = queued_by_user and status in ("queued", "prepared")
                if status in (
                    "queued", "accepted", "generating", "completed", "interrupted",
                    "unavailable", "outcome_unknown", "stopped",
                ):
                    item["status"] = status
                elif status == "prepared":
                    item["status"] = "queued"
                elif status == "dispatching":
                    item["status"] = "accepted"
                item["needs_attention"] = status in (
                    "preflight_failed", "outcome_unknown", "interrupted", "unavailable",
                )
            else:
                item["queued_followup"] = False
                item["status"] = visible_reply_status(*original_live[send_id], now=time.time())
                item["needs_attention"] = item["status"] in (
                    "interrupted", "unavailable", "outcome_unknown",
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
