"""Durable, one-shot user-requested read-only transcript checks."""

import sqlalchemy as sa
from alembic import op

revision = "results_0003"
down_revision = "results_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "manual_recovery_requests" not in inspector.get_table_names():
        op.create_table(
            "manual_recovery_requests",
            sa.Column("target_id", sa.String(), nullable=False, primary_key=True),
            sa.Column("send_id", sa.String(), nullable=False),
            sa.Column("requested_at", sa.Float(), nullable=False),
        )
    if "manual_recovery_requests_run" not in {
        index["name"] for index in sa.inspect(op.get_bind()).get_indexes("manual_recovery_requests")
    }:
        op.create_index(
            "manual_recovery_requests_run", "manual_recovery_requests", ["send_id"], unique=False,
        )


def downgrade() -> None:
    op.drop_index("manual_recovery_requests_run", table_name="manual_recovery_requests")
    op.drop_table("manual_recovery_requests")
