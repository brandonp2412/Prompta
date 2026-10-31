"""Adopt or create the durable owned-tab ledger."""

import sqlalchemy as sa
from alembic import op

revision = "ownership_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    if not sa.inspect(op.get_bind()).has_table("owned_tabs"):
        op.create_table(
            "owned_tabs",
            sa.Column("target_id", sa.Text, primary_key=True),
            sa.Column("opened_at", sa.Float, nullable=False),
        )


def downgrade() -> None:
    op.drop_table("owned_tabs")
