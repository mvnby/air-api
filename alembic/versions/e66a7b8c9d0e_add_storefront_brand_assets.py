"""Scope storefront brand media and reference it from public site settings.

Revision ID: e66a7b8c9d0e
Revises: e65f6a7b8c9d
"""

from alembic import op
import sqlalchemy as sa


revision = "e66a7b8c9d0e"
down_revision = "e65f6a7b8c9d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media_asset", sa.Column("tenant_id", sa.Integer(), nullable=True))
    op.add_column("media_asset", sa.Column("storefront_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_media_asset_tenant_id", "media_asset", "tenant", ["tenant_id"], ["id"])
    op.create_foreign_key("fk_media_asset_storefront_scope", "media_asset", "storefront", ["storefront_id", "tenant_id"], ["id", "tenant_id"])
    op.create_index("ix_media_asset_tenant_id", "media_asset", ["tenant_id"])
    op.create_index("ix_media_asset_storefront_id", "media_asset", ["storefront_id"])
    op.add_column("storefront_settings", sa.Column("logo_asset_id", sa.Integer(), nullable=True))
    op.add_column("storefront_settings", sa.Column("compact_logo_asset_id", sa.Integer(), nullable=True))
    op.create_foreign_key("fk_storefront_settings_logo_asset_id", "storefront_settings", "media_asset", ["logo_asset_id"], ["id"])
    op.create_foreign_key("fk_storefront_settings_compact_logo_asset_id", "storefront_settings", "media_asset", ["compact_logo_asset_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_storefront_settings_compact_logo_asset_id", "storefront_settings", type_="foreignkey")
    op.drop_constraint("fk_storefront_settings_logo_asset_id", "storefront_settings", type_="foreignkey")
    op.drop_column("storefront_settings", "compact_logo_asset_id")
    op.drop_column("storefront_settings", "logo_asset_id")
    op.drop_index("ix_media_asset_storefront_id", table_name="media_asset")
    op.drop_index("ix_media_asset_tenant_id", table_name="media_asset")
    op.drop_constraint("fk_media_asset_storefront_scope", "media_asset", type_="foreignkey")
    op.drop_constraint("fk_media_asset_tenant_id", "media_asset", type_="foreignkey")
    op.drop_column("media_asset", "storefront_id")
    op.drop_column("media_asset", "tenant_id")
