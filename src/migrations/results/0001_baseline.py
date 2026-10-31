"""Baseline results schema; adopt pre-Alembic installations without replacing tables."""

import sqlalchemy as sa
from alembic import op

revision = "results_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "job_responses" not in existing:
        op.create_table(
            "job_responses",
            sa.Column("send_id", sa.String(), nullable=False, primary_key=True),
            sa.Column("job_name", sa.String(), nullable=False),
            sa.Column("user_text", sa.Text(), nullable=False),
            sa.Column("assistant_text", sa.Text(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("source", sa.String(), nullable=False),
            sa.Column("conversation_id", sa.String(), nullable=False),
            sa.Column("message_id", sa.String(), nullable=False),
            sa.Column("parent_id", sa.String(), nullable=False),
            sa.Column("created_at", sa.Float(), nullable=False),
            sa.Column("accepted_at", sa.Float(), nullable=False),
            sa.Column("updated_at", sa.Float(), nullable=False),
            sa.Column("finished_at", sa.Float(), nullable=False),
            sa.Column("capture_owner", sa.String(), nullable=False),
            sa.Column("capture_deadline", sa.Float(), nullable=False),
        )
    if "local_chat_pins" not in existing:
        op.create_table(
            "local_chat_pins",
            sa.Column("send_id", sa.String(), nullable=False, primary_key=True),
            sa.Column("pinned_at", sa.Float(), nullable=False),
        )
    if "local_chat_reads" not in existing:
        op.create_table(
            "local_chat_reads",
            sa.Column("send_id", sa.String(), nullable=False, primary_key=True),
            sa.Column("seen_revision", sa.String(length=64), nullable=False),
            sa.Column("read_at", sa.Float(), nullable=False),
        )
    if "history_recovery_attempts" not in existing:
        op.create_table(
            "history_recovery_attempts",
            sa.Column("send_id", sa.String(), nullable=False, primary_key=True),
            sa.Column("attempt_count", sa.Integer(), nullable=False),
            sa.Column("next_attempt_at", sa.Float(), nullable=False),
            sa.Column("last_attempt_at", sa.Float(), nullable=False),
        )
    if "manual_reply_turns" not in existing:
        op.create_table(
            "manual_reply_turns",
            sa.Column("reply_id", sa.String(), nullable=False, primary_key=True),
            sa.Column("send_id", sa.String(), nullable=False),
            sa.Column("conversation_id", sa.String(), nullable=False),
            sa.Column("parent_id", sa.String(), nullable=False),
            sa.Column("user_text", sa.Text(), nullable=False),
            sa.Column("assistant_text", sa.Text(), nullable=False),
            sa.Column("message_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("lease_owner", sa.String(), nullable=False),
            sa.Column("lease_deadline", sa.Float(), nullable=False),
            sa.Column("created_at", sa.Float(), nullable=False),
            sa.Column("updated_at", sa.Float(), nullable=False),
        )
    if "job_responses_active" not in {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("job_responses")
    }:
        op.create_index(
            "job_responses_active", "job_responses", ["status", "capture_deadline"], unique=False
        )
    if "manual_reply_turns_branch" not in {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("manual_reply_turns")
    }:
        op.create_index(
            "manual_reply_turns_branch",
            "manual_reply_turns",
            ["send_id", "created_at"],
            unique=False,
        )


def downgrade() -> None:
    op.drop_table("manual_reply_turns")
    op.drop_table("history_recovery_attempts")
    op.drop_table("local_chat_reads")
    op.drop_table("local_chat_pins")
    op.drop_table("job_responses")
