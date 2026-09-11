"""Add normalized multi-series scopes for warranty policies.

Revision ID: e56b2c3d4e5
Revises: e55b1c2d3e4f
"""

from alembic import op
import sqlalchemy as sa


revision = "e56b2c3d4e5"
down_revision = "e55b1c2d3e4f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "warranty_policy_series_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("policy_id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["policy_id"], ["warranty_policy.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["series_id"], ["product_series.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("policy_id", "series_id", name="uq_warranty_policy_series_link"),
    )
    op.create_index("ix_warranty_policy_series_link_policy_id", "warranty_policy_series_link", ["policy_id"])
    op.create_index("ix_warranty_policy_series_link_series_id", "warranty_policy_series_link", ["series_id"])
    op.create_index(
        "ix_warranty_policy_series_link_series_policy",
        "warranty_policy_series_link",
        ["series_id", "policy_id"],
    )
    op.execute(
        "INSERT INTO warranty_policy_series_link (policy_id, series_id, sort_order) "
        "SELECT id, series_id, 0 FROM warranty_policy WHERE series_id IS NOT NULL"
    )


def downgrade() -> None:
    op.drop_index("ix_warranty_policy_series_link_series_policy", table_name="warranty_policy_series_link")
    op.drop_index("ix_warranty_policy_series_link_series_id", table_name="warranty_policy_series_link")
    op.drop_index("ix_warranty_policy_series_link_policy_id", table_name="warranty_policy_series_link")
    op.drop_table("warranty_policy_series_link")
