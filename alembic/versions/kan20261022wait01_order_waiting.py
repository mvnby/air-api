"""Add nullable waiting metadata and a shared order workflow revision; no backfill."""

from alembic import op
import sqlalchemy as sa

revision = "kan20261022wait01"
down_revision = "cat20261019feat03"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "order", sa.Column("on_hold_reason_code", sa.String(40), nullable=True)
    )
    op.add_column(
        "order", sa.Column("on_hold_started_at", sa.DateTime(), nullable=True)
    )
    op.add_column(
        "order",
        sa.Column(
            "workflow_revision", sa.Integer(), nullable=False, server_default="0"
        ),
    )


def downgrade():
    op.drop_column("order", "workflow_revision")
    op.drop_column("order", "on_hold_started_at")
    op.drop_column("order", "on_hold_reason_code")
