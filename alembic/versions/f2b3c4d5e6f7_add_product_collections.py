"""add product collections

Revision ID: f2b3c4d5e6f7
Revises: f1a2b3c4d5e6
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f2b3c4d5e6f7"
down_revision: str | None = "f1a2b3c4d5e6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product",
        sa.Column(
            "product_kind",
            sa.String(length=40),
            nullable=False,
            server_default="unknown",
        ),
    )
    op.create_index("ix_product_product_kind", "product", ["product_kind"], unique=False)
    op.execute(
        """
        UPDATE product
        SET product_kind = CASE
            WHEN lower(COALESCE(specs::jsonb ->> 'includes_indoor_unit', '')) IN
                 ('true', '1', 'yes', 'да', 'есть', 'в комплекте')
             AND lower(COALESCE(specs::jsonb ->> 'includes_outdoor_unit', '')) IN
                 ('true', '1', 'yes', 'да', 'есть', 'в комплекте')
                THEN 'complete_split_system'
            WHEN lower(COALESCE(specs::jsonb ->> 'includes_indoor_unit', '')) IN
                 ('true', '1', 'yes', 'да', 'есть', 'в комплекте')
             AND lower(COALESCE(specs::jsonb ->> 'includes_outdoor_unit', '')) IN
                 ('false', '0', 'no', 'нет', 'не входит')
                THEN 'indoor_unit'
            WHEN lower(COALESCE(specs::jsonb ->> 'includes_indoor_unit', '')) IN
                 ('false', '0', 'no', 'нет', 'не входит')
             AND lower(COALESCE(specs::jsonb ->> 'includes_outdoor_unit', '')) IN
                 ('true', '1', 'yes', 'да', 'есть', 'в комплекте')
                THEN 'outdoor_unit'
            ELSE 'unknown'
        END
        """
    )

    op.create_table(
        "product_collection",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=120), nullable=False),
        sa.Column("internal_name", sa.String(length=180), nullable=False),
        sa.Column("public_title", sa.String(length=180), nullable=False),
        sa.Column("public_description", sa.Text(), nullable=True),
        sa.Column("public_badge", sa.String(length=80), nullable=True),
        sa.Column("cta_label", sa.String(length=80), nullable=True),
        sa.Column("cta_url", sa.String(length=500), nullable=True),
        sa.Column("editorial_note", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("mode", sa.String(length=24), nullable=False),
        sa.Column("min_items", sa.Integer(), nullable=False),
        sa.Column("max_items", sa.Integer(), nullable=False),
        sa.Column("fallback_collection_id", sa.Integer(), nullable=True),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_product_collection_status",
        ),
        sa.CheckConstraint(
            "mode IN ('manual', 'automatic', 'hybrid')",
            name="ck_product_collection_mode",
        ),
        sa.CheckConstraint(
            "min_items >= 1 AND max_items >= min_items AND max_items <= 24",
            name="ck_product_collection_item_limits",
        ),
        sa.ForeignKeyConstraint(
            ["fallback_collection_id"],
            ["product_collection.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_product_collection_slug"),
    )
    for column in ("slug", "internal_name", "status", "mode", "fallback_collection_id", "starts_at", "ends_at", "updated_at"):
        op.create_index(f"ix_product_collection_{column}", "product_collection", [column], unique=False)

    op.create_table(
        "product_collection_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_pinned", sa.Boolean(), nullable=False),
        sa.Column("editorial_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["product_collection.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "collection_id",
            "product_id",
            name="uq_product_collection_item_product",
        ),
        sa.UniqueConstraint(
            "collection_id",
            "position",
            name="uq_product_collection_item_position",
        ),
    )
    for column in ("collection_id", "product_id", "position"):
        op.create_index(f"ix_product_collection_item_{column}", "product_collection_item", [column], unique=False)

    op.create_table(
        "product_collection_placement",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("surface_key", sa.String(length=80), nullable=False),
        sa.Column("slot_key", sa.String(length=80), nullable=False),
        sa.Column("collection_id", sa.Integer(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["collection_id"], ["product_collection.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "surface_key",
            "slot_key",
            "collection_id",
            name="uq_product_collection_placement_slot",
        ),
    )
    for column in ("surface_key", "slot_key", "collection_id", "position", "is_enabled", "starts_at", "ends_at"):
        op.create_index(
            f"ix_product_collection_placement_{column}",
            "product_collection_placement",
            [column],
            unique=False,
        )

    op.alter_column("product", "product_kind", server_default=None)


def downgrade() -> None:
    op.drop_table("product_collection_placement")
    op.drop_table("product_collection_item")
    op.drop_table("product_collection")
    op.drop_index("ix_product_product_kind", table_name="product")
    op.drop_column("product", "product_kind")
