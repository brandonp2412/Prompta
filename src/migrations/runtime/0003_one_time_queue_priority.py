"""Persist one-time job queue priority across removed schedule definitions."""

import sqlalchemy as sa
from alembic import op

revision = "runtime_0003"
down_revision = "runtime_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_deliveries",
        sa.Column("one_time", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("job_deliveries", "one_time")
