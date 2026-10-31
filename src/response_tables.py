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
    column,
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
_reply_attention = table("manual_reply_turns", column("send_id"), column("status"))
_attention_filter = or_(
    results.c.status.in_(("interrupted", "unavailable")),
    select(_reply_attention.c.send_id)
    .where(
        _reply_attention.c.send_id == results.c.send_id,
        _reply_attention.c.status.in_(
            (
                "preflight_failed",
                "outcome_unknown",
                "interrupted",
                "unavailable",
            )
        ),
    )
    .exists(),
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
history_recovery_attempts = Table(
    "history_recovery_attempts",
    _SCHEMA,
    Column("send_id", String, primary_key=True),
    Column("attempt_count", Integer, nullable=False, default=0),
    Column("next_attempt_at", Float, nullable=False, default=0),
    Column("last_attempt_at", Float, nullable=False, default=0),
)
