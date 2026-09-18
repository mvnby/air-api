"""Add anonymous daily catalog-workspace pilot aggregates.

Revision ID: e62c3d4e5f6
Revises: e61d4e5f6a7
"""

from alembic import op
import sqlalchemy as sa


revision = "e62c3d4e5f6"
down_revision = "e61d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "catalog_workspace_usage_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("layout_version", sa.String(24), nullable=False),
        sa.Column("device", sa.String(12), nullable=False),
        sa.Column("action", sa.String(32), nullable=False),
        sa.Column("outcome", sa.String(16), nullable=False),
        sa.Column("duration_bucket", sa.String(16), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("count > 0", name="ck_catalog_usage_positive_count"),
        sa.UniqueConstraint(
            "day", "layout_version", "device", "action", "outcome", "duration_bucket",
            name="uq_catalog_usage_dimensions",
        ),
    )
    op.create_index("ix_catalog_usage_day", "catalog_workspace_usage_daily", ["day"])
    op.create_index("ix_catalog_usage_day_id", "catalog_workspace_usage_daily", ["day", "id"])


def downgrade() -> None:
    op.drop_index("ix_catalog_usage_day_id", table_name="catalog_workspace_usage_daily")
    op.drop_index("ix_catalog_usage_day", table_name="catalog_workspace_usage_daily")
    op.drop_table("catalog_workspace_usage_daily")
