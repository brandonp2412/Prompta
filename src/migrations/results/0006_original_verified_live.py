"""Track verified active original responses after capture recovery."""

import sqlalchemy as sa
from alembic import op

revision = "results_0006"
down_revision = "results_0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("job_responses", sa.Column(
        "live_observed_at", sa.Float(), nullable=False, server_default="0",
    ))


def downgrade() -> None:
    op.drop_column("job_responses", "live_observed_at")
