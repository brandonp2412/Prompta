"""Save user-visible assistant text and tool headings in transcript order."""

import sqlalchemy as sa
from alembic import op

revision = "results_0005"
down_revision = "results_0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("job_responses", "manual_reply_turns"):
        columns = {item["name"] for item in sa.inspect(op.get_bind()).get_columns(table)}
        if "display_blocks_json" not in columns:
            op.add_column(table, sa.Column(
                "display_blocks_json", sa.Text(), nullable=False, server_default="[]"))


def downgrade() -> None:
    op.drop_column("manual_reply_turns", "display_blocks_json")
    op.drop_column("job_responses", "display_blocks_json")
