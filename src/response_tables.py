"""Tables shared by result and reply persistence."""

from sqlalchemy import (
    Column,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    and_,
    cast,
    column,
    func,
    or_,
    select,
    table,
)

_SCHEMA = MetaData()
results = Table(
    "job_responses",
    _SCHEMA,
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
_reply_attention = table(
    "manual_reply_turns", column("send_id"), column("reply_id"),
    column("status"), column("created_at"), column("live_observed_at"),
)
_latest_reply = (select(_reply_attention.c.status)
                 .where(_reply_attention.c.send_id == results.c.send_id)
                 .order_by(_reply_attention.c.created_at.desc(),
                           _reply_attention.c.reply_id.desc())
                 .limit(1).scalar_subquery())
_latest_live_at = (select(_reply_attention.c.live_observed_at)
                   .where(_reply_attention.c.send_id == results.c.send_id)
                   .order_by(_reply_attention.c.created_at.desc(),
                             _reply_attention.c.reply_id.desc())
                   .limit(1).scalar_subquery())
_live_cutoff = cast(func.strftime("%s", "now"), Float) - 10 * 60
_attention_filter = or_(
    and_(_latest_reply.is_(None),
         results.c.status.in_(("interrupted", "unavailable", "outcome_unknown"))),
    _latest_reply.in_(("preflight_failed", "unavailable")),
    and_(_latest_reply.in_(("outcome_unknown", "interrupted")),
         _latest_live_at <= _live_cutoff),
)
local_chat_pins = Table(
    "local_chat_pins",
    _SCHEMA,
    Column("send_id", String, primary_key=True),
    Column("pinned_at", Float, nullable=False),
)
local_chat_reads = Table(
    "local_chat_reads",
    _SCHEMA,
    Column("send_id", String, primary_key=True),
    Column("seen_revision", String(64), nullable=False),
    Column("read_at", Float, nullable=False),
)
manual_recovery_requests = Table(
    "manual_recovery_requests",
    _SCHEMA,
    Column("target_id", String, primary_key=True),
    Column("send_id", String, nullable=False),
    Column("requested_at", Float, nullable=False),
)

history_recovery_attempts = Table(
    "history_recovery_attempts",
    _SCHEMA,
    Column("send_id", String, primary_key=True),
    Column("attempt_count", Integer, nullable=False, default=0),
    Column("next_attempt_at", Float, nullable=False, default=0),
    Column("last_attempt_at", Float, nullable=False, default=0),
)
