"""Add isolated public storefront settings without changing existing configuration.

Revision ID: e58a1b2c3d4
Revises: e57c3d4e5f6
"""

from alembic import op
import sqlalchemy as sa

revision = "e58a1b2c3d4"
down_revision = "e57c3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "storefront_settings",
        sa.Column("storefront_id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("display_name", sa.String(160), nullable=False),
        sa.Column("city", sa.String(120), nullable=False),
        sa.Column("phone", sa.String(80), nullable=False),
        sa.Column("email", sa.String(254), nullable=False),
        sa.Column("address", sa.String(500), nullable=False),
        sa.Column("work_hours", sa.String(300), nullable=False),
        sa.Column("support_telegram_url", sa.String(300), nullable=False),
        sa.Column("services", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["storefront_id", "tenant_id"], ["storefront.id", "storefront.tenant_id"], name="fk_storefront_settings_scope"),
    )
    op.create_index("ix_storefront_settings_tenant_id", "storefront_settings", ["tenant_id"])


def downgrade() -> None:
    op.drop_table("storefront_settings")
