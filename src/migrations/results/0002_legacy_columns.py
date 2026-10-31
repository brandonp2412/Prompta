"""Upgrade legacy results columns while preserving existing records."""

import sqlalchemy as sa
from alembic import op

revision = "results_0002"
down_revision = "results_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("job_responses")}
    if "tool_calls_json" not in columns:
        op.add_column(
            "job_responses",
            sa.Column("tool_calls_json", sa.Text(), nullable=False, server_default="[]"),
        )
    columns = {
        column["name"] for column in sa.inspect(op.get_bind()).get_columns("manual_reply_turns")
    }
    if "tool_calls_json" not in columns:
        op.add_column(
            "manual_reply_turns",
            sa.Column("tool_calls_json", sa.Text(), nullable=False, server_default="[]"),
        )
    if "response_parent_id" not in columns:
        op.add_column(
            "manual_reply_turns",
            sa.Column("response_parent_id", sa.String(), nullable=False, server_default=""),
        )
    if "queued_by_user" not in columns:
        op.add_column(
            "manual_reply_turns",
            sa.Column("queued_by_user", sa.Boolean(), nullable=False, server_default="0"),
        )


def downgrade() -> None:
    op.drop_column("manual_reply_turns", "queued_by_user")
    op.drop_column("manual_reply_turns", "response_parent_id")
    op.drop_column("manual_reply_turns", "tool_calls_json")
    op.drop_column("job_responses", "tool_calls_json")
