"""Baseline runtime schema; adopt pre-Alembic installations without replacing tables."""

import sqlalchemy as sa
from alembic import op

revision = "runtime_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    existing = set(sa.inspect(op.get_bind()).get_table_names())
    if "scheduled_jobs" not in existing:
        op.create_table(
            "scheduled_jobs",
            sa.Column("name", sa.String(), nullable=False, primary_key=True),
            sa.Column("prompt", sa.Text(), nullable=False),
            sa.Column("interval_seconds", sa.Float(), nullable=False),
            sa.Column("daily_at", sa.String(), nullable=True),
            sa.Column("exact_interval", sa.Boolean(), nullable=False),
            sa.Column("run_at_epoch", sa.Float(), nullable=True),
        )
    if "scheduler_state" not in existing:
        op.create_table(
            "scheduler_state",
            sa.Column("scope", sa.String(), nullable=False, primary_key=True),
            sa.Column("name", sa.String(), nullable=False, primary_key=True),
            sa.Column("key", sa.String(), nullable=False, primary_key=True),
            sa.Column("value_json", sa.Text(), nullable=False),
        )
    if "account_state" not in existing:
        op.create_table(
            "account_state",
            sa.Column("key", sa.String(), nullable=False, primary_key=True),
            sa.Column("value_json", sa.Text(), nullable=False),
        )
    if "job_deliveries" not in existing:
        op.create_table(
            "job_deliveries",
            sa.Column("sequence", sa.Integer(), nullable=False, primary_key=True),
            sa.Column("send_id", sa.String(), nullable=False, unique=True),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("client_id", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("error", sa.Text(), nullable=False),
            sa.Column("last_error", sa.Text(), nullable=False),
            sa.Column("created_at", sa.Float(), nullable=False),
            sa.Column("updated_at", sa.Float(), nullable=False),
            sa.Column("retry_at", sa.Float(), nullable=False),
            sa.Column("retry_attempt", sa.Integer(), nullable=False),
            sa.Column("finished_at", sa.Float(), nullable=False),
            sa.Column("lease_owner", sa.String(), nullable=False),
            sa.Column("lease_acquired_at", sa.Float(), nullable=False),
            sa.Column("lease_expires_at", sa.Float(), nullable=False),
        )
    if "service_health" not in existing:
        op.create_table(
            "service_health",
            sa.Column("service", sa.String(), nullable=False, primary_key=True),
            sa.Column("heartbeat_at", sa.Float(), nullable=False),
            sa.Column("activity", sa.String(), nullable=False),
            sa.Column("activity_started_at", sa.Float(), nullable=False),
        )
    if "job_deliveries_claimable" not in {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("job_deliveries")
    }:
        op.create_index(
            "job_deliveries_claimable",
            "job_deliveries",
            ["status", "retry_at", "lease_expires_at", "sequence"],
            unique=False,
        )
    if "job_deliveries_client_id" not in {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("job_deliveries")
    }:
        op.create_index(
            "job_deliveries_client_id",
            "job_deliveries",
            ["client_id"],
            unique=True,
            sqlite_where=sa.text("client_id != ''"),
        )


def downgrade() -> None:
    op.drop_table("service_health")
    op.drop_table("job_deliveries")
    op.drop_table("account_state")
    op.drop_table("scheduler_state")
    op.drop_table("scheduled_jobs")
