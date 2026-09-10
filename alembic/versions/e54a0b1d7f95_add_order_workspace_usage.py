"""Add content-free, storefront-scoped daily order usage counters.

Revision ID: e54a0b1d7f95
Revises: d43f9a0c6e84
"""

from alembic import op
import sqlalchemy as sa

revision = "e54a0b1d7f95"
down_revision = "d43f9a0c6e84"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_workspace_usage_daily",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("layout_version", sa.String(24), nullable=False),
        sa.Column("workflow", sa.String(24), nullable=False),
        sa.Column("party_kind", sa.String(32), nullable=False),
        sa.Column("viewport", sa.String(12), nullable=False),
        sa.Column("metric", sa.String(32), nullable=False),
        sa.Column("count", sa.BigInteger(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.ForeignKeyConstraint(["storefront_id", "tenant_id"], ["storefront.id", "storefront.tenant_id"], name="fk_order_usage_storefront_tenant", ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("count > 0", name="ck_order_usage_positive_count"),
        sa.UniqueConstraint("tenant_id", "storefront_id", "day", "layout_version", "workflow", "party_kind", "viewport", "metric", name="uq_order_usage_dimensions"),
    )
    op.create_index("ix_order_usage_scope_day", "order_workspace_usage_daily", ["tenant_id", "storefront_id", "day"])
    op.create_index("ix_order_usage_day_id", "order_workspace_usage_daily", ["day", "id"])


def downgrade() -> None:
    op.drop_index("ix_order_usage_day_id", table_name="order_workspace_usage_daily")
    op.drop_index("ix_order_usage_scope_day", table_name="order_workspace_usage_daily")
    op.drop_table("order_workspace_usage_daily")
