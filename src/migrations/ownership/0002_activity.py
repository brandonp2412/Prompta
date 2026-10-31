"""Preserve the last verified activity clock across legacy upgrades."""

import sqlalchemy as sa
from alembic import op

revision = "ownership_0002"
down_revision = "ownership_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    columns = {column["name"] for column in sa.inspect(op.get_bind()).get_columns("owned_tabs")}
    if "last_activity_at" not in columns:
        op.add_column(
            "owned_tabs",
            sa.Column("last_activity_at", sa.Float, nullable=False, server_default="0"),
        )
        op.execute(sa.text("UPDATE owned_tabs SET last_activity_at = opened_at"))


def downgrade() -> None:
    op.drop_column("owned_tabs", "last_activity_at")
