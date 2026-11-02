"""Persist explicit bump-to-front ordering."""

import sqlalchemy as sa
from alembic import op

revision = "runtime_0004"
down_revision = "runtime_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "job_deliveries",
        sa.Column("queue_priority", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("job_deliveries", "queue_priority")
