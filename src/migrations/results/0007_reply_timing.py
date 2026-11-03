"""Record accepted and completed timestamps for reply work duration."""

import sqlalchemy as sa
from alembic import op

revision = "results_0007"
down_revision = "results_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for name in ("accepted_at", "finished_at"):
        op.add_column(
            "manual_reply_turns",
            sa.Column(
                name,
                sa.Float(),
                nullable=False,
                server_default="0",
            ),
        )


def downgrade() -> None:
    op.drop_column("manual_reply_turns", "finished_at")
    op.drop_column("manual_reply_turns", "accepted_at")
