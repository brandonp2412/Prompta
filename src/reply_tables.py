from __future__ import annotations

from sqlalchemy import Boolean, Column, Float, Index, MetaData, String, Table, Text

_SCHEMA = MetaData()
replies = Table(
    "manual_reply_turns",
    _SCHEMA,
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
