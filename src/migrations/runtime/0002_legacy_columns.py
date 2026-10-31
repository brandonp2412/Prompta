"""Upgrade legacy runtime columns while preserving existing records."""

import sqlalchemy as sa
from alembic import op

revision = "runtime_0002"
down_revision = "runtime_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("scheduled_jobs")}
    if "pin_chat" not in columns:
        op.add_column(
            "scheduled_jobs",
            sa.Column("pin_chat", sa.Boolean(), nullable=False, server_default="0"),
        )
    if "source_revision" not in columns:
        op.add_column(
            "scheduled_jobs",
            sa.Column("source_revision", sa.String(), nullable=False, server_default=""),
        )
    if "mutex_group" not in columns:
        op.add_column(
            "scheduled_jobs",
            sa.Column("mutex_group", sa.String(), nullable=False, server_default=""),
        )
    if "images_json" not in columns:
        op.add_column(
            "scheduled_jobs",
            sa.Column("images_json", sa.Text(), nullable=False, server_default="[]"),
        )
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("job_deliveries")}
    if "images_json" not in columns:
        op.add_column(
            "job_deliveries",
            sa.Column("images_json", sa.Text(), nullable=False, server_default="[]"),
        )
    if "pin_chat" not in columns:
        op.add_column(
            "job_deliveries",
            sa.Column("pin_chat", sa.Boolean(), nullable=False, server_default="0"),
        )
    # Transfer the old scheduler-wide read gate only once; never shorten a newer gate.
    op.execute(
        sa.text("""
        INSERT INTO account_state (key, value_json)
        SELECT 'rate_limit_backoff', value_json FROM scheduler_state
        WHERE scope = 'scheduler' AND name = '' AND key = 'rate_limit_backoff'
        ON CONFLICT(key) DO NOTHING
    """)
    )


def downgrade() -> None:
    op.drop_column("job_deliveries", "pin_chat")
    op.drop_column("job_deliveries", "images_json")
    op.drop_column("scheduled_jobs", "images_json")
    op.drop_column("scheduled_jobs", "mutex_group")
    op.drop_column("scheduled_jobs", "source_revision")
    op.drop_column("scheduled_jobs", "pin_chat")
