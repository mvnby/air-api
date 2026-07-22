"""add canonical feature contract

Revision ID: e46f8a1c2d30
Revises: c35e9a2b7d41
Create Date: 2026-07-22 10:00:00.000000

The legacy brand_feature tables intentionally remain during the expand phase.
Production applies migrations before the blue-green application switch, so
dropping them here would break the still-active previous release.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e46f8a1c2d30"
down_revision: Union[str, Sequence[str], None] = "c35e9a2b7d41"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _link_columns(target_name: str, target_table: str) -> list[sa.Column]:
    return [
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column(target_name, sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(), nullable=False, server_default="manual"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("override_title", sa.String(), nullable=True),
        sa.Column("override_description", sa.Text(), nullable=True),
        sa.Column("override_media_id", sa.Integer(), nullable=True),
        sa.Column("override_image_url", sa.String(), nullable=True),
        sa.Column("override_icon", sa.String(), nullable=True),
        sa.Column("override_footnote", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint([target_name], [f"{target_table}.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["feature_id"], ["feature.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["override_media_id"], ["media_asset.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint(
            "source IN ('manual', 'inherited', 'derived')",
            name=f"ck_feature_{target_table.replace('product_', '')}_link_source",
        ),
        sa.UniqueConstraint(target_name, "feature_id", name=f"uq_feature_{target_table.replace('product_', '')}_link"),
    ]


def upgrade() -> None:
    op.create_table(
        "feature_category",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_feature_category_slug", "feature_category", ["slug"], unique=True)
    op.create_index("ix_feature_category_name", "feature_category", ["name"], unique=False)
    op.create_index("ix_feature_category_sort_order", "feature_category", ["sort_order"], unique=False)
    op.create_index("ix_feature_category_is_active", "feature_category", ["is_active"], unique=False)

    op.bulk_insert(
        sa.table(
            "feature_category",
            sa.column("slug", sa.String()),
            sa.column("name", sa.String()),
            sa.column("sort_order", sa.Integer()),
        ),
        [
            {"slug": "comfort", "name": "Комфорт", "sort_order": 10},
            {"slug": "control", "name": "Управление", "sort_order": 20},
            {"slug": "air-quality", "name": "Очистка воздуха", "sort_order": 30},
            {"slug": "efficiency", "name": "Энергоэффективность", "sort_order": 40},
            {"slug": "performance", "name": "Производительность", "sort_order": 50},
            {"slug": "reliability", "name": "Надёжность", "sort_order": 60},
            {"slug": "installation", "name": "Монтаж", "sort_order": 70},
            {"slug": "design", "name": "Дизайн", "sort_order": 80},
        ],
    )

    op.create_table(
        "feature",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("short_description", sa.Text(), nullable=True),
        sa.Column("full_description", sa.Text(), nullable=True),
        sa.Column("category_id", sa.Integer(), nullable=False),
        sa.Column("scope_type", sa.String(), nullable=False, server_default="universal"),
        sa.Column("brand_id", sa.Integer(), nullable=True),
        sa.Column("icon_media_id", sa.Integer(), nullable=True),
        sa.Column("image_media_id", sa.Integer(), nullable=True),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("video_url", sa.String(), nullable=True),
        sa.Column("footnote", sa.String(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False, server_default=sa.text("'[]'::json")),
        sa.Column("seo_title", sa.String(), nullable=True),
        sa.Column("seo_description", sa.Text(), nullable=True),
        sa.Column("source_notes", sa.Text(), nullable=True),
        sa.Column("legal_notes", sa.Text(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("archived_at", sa.DateTime(), nullable=True),
        sa.CheckConstraint(
            "scope_type IN ('universal', 'brand', 'series', 'product', 'derived')",
            name="ck_feature_scope_type",
        ),
        sa.ForeignKeyConstraint(["brand_id"], ["brand.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["category_id"], ["feature_category.id"]),
        sa.ForeignKeyConstraint(["icon_media_id"], ["media_asset.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["image_media_id"], ["media_asset.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("name", "category_id", "scope_type", "brand_id", "is_active", "sort_order", "archived_at"):
        op.create_index(f"ix_feature_{column}", "feature", [column], unique=False)
    op.create_index("ix_feature_slug", "feature", ["slug"], unique=True)

    op.create_table(
        "feature_rule",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("spec_key", sa.String(), nullable=False),
        sa.Column("operator", sa.String(), nullable=False),
        sa.Column("target_value", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "operator IN ('eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'in', 'contains', 'exists')",
            name="ck_feature_rule_operator",
        ),
        sa.ForeignKeyConstraint(["feature_id"], ["feature.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("feature_id", "spec_key", "operator", name="uq_feature_rule_definition"),
    )
    for column in ("feature_id", "spec_key", "operator", "is_active"):
        op.create_index(f"ix_feature_rule_{column}", "feature_rule", [column], unique=False)

    for table_name, target_name, target_table in (
        ("feature_brand_link", "brand_id", "brand"),
        ("feature_series_link", "series_id", "product_series"),
        ("feature_product_link", "product_id", "product"),
    ):
        op.create_table(table_name, *_link_columns(target_name, target_table))
        for column in (target_name, "feature_id", "source", "is_enabled", "sort_order"):
            op.create_index(f"ix_{table_name}_{column}", table_name, [column], unique=False)

    # Preserve existing ids. Duplicate slugs across brands receive a stable id suffix.
    op.execute(
        """
        INSERT INTO feature (
            id, slug, name, full_description, category_id, scope_type, brand_id,
            icon, image_url, footnote, source_url, aliases, is_active, sort_order,
            created_at, updated_at
        )
        SELECT
            bf.id,
            CASE WHEN COUNT(*) OVER (PARTITION BY bf.slug) = 1
                 THEN bf.slug ELSE bf.slug || '-' || bf.id::text END,
            bf.title,
            bf.text,
            (SELECT id FROM feature_category WHERE slug = 'comfort'),
            'brand',
            bf.brand_id,
            bf.icon,
            bf.image_url,
            bf.footnote,
            bf.source_url,
            bf.aliases,
            bf.is_published,
            bf.sort_order,
            bf.created_at,
            bf.updated_at
        FROM brand_feature bf
        """
    )
    op.execute(
        """
        INSERT INTO feature_brand_link (
            brand_id, feature_id, source, is_enabled, sort_order, created_at, updated_at
        )
        SELECT brand_id, id, 'manual', is_published, sort_order, created_at, updated_at
        FROM brand_feature
        """
    )
    op.execute(
        """
        INSERT INTO feature_series_link (
            series_id, feature_id, source, is_enabled, sort_order,
            override_title, override_description, override_image_url,
            override_icon, override_footnote, created_at, updated_at
        )
        SELECT
            series_id, feature_id, 'manual', true, sort_order,
            title_override, text_override, image_url_override,
            icon_override, footnote_override, created_at, created_at
        FROM product_series_feature_link
        """
    )
    op.execute("SELECT setval(pg_get_serial_sequence('feature', 'id'), COALESCE(MAX(id), 1), MAX(id) IS NOT NULL) FROM feature")


def downgrade() -> None:
    for table_name in ("feature_product_link", "feature_series_link", "feature_brand_link"):
        op.drop_table(table_name)
    op.drop_table("feature_rule")
    op.drop_table("feature")
    op.drop_table("feature_category")
