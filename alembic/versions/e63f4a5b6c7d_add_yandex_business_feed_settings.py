"""add system-scoped Yandex Business feed settings

Revision ID: e63f4a5b6c7d
Revises: e62c3d4e5f6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "e63f4a5b6c7d"
down_revision: str | None = "e62c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | None = None


def upgrade() -> None:
    op.create_table(
        "yandex_business_feed_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column(
            "selection_mode",
            sa.String(length=32),
            nullable=False,
            server_default="all_published",
        ),
        sa.Column("include_services", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("require_ready_image", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("require_in_stock", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "selection_mode IN ('all_published', 'curated_collections')",
            name="ck_yandex_business_feed_settings_selection_mode",
        ),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_yandex_business_feed_settings_storefront_tenant",
        ),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "tenant_id",
            "storefront_id",
            name="uq_yandex_business_feed_settings_scope",
        ),
    )
    op.create_index(
        "ix_yandex_business_feed_settings_tenant_id",
        "yandex_business_feed_settings",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        "ix_yandex_business_feed_settings_storefront_id",
        "yandex_business_feed_settings",
        ["storefront_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_yandex_business_feed_settings_storefront_id",
        table_name="yandex_business_feed_settings",
    )
    op.drop_index(
        "ix_yandex_business_feed_settings_tenant_id",
        table_name="yandex_business_feed_settings",
    )
    op.drop_table("yandex_business_feed_settings")
