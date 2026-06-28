"""add brand feature library

Revision ID: d1e2f3a4b5c6
Revises: c9d0e1f2a3b4
Create Date: 2026-06-28 02:45:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "d1e2f3a4b5c6"
down_revision: Union[str, Sequence[str], None] = "c9d0e1f2a3b4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brand_feature",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("icon", sa.String(), nullable=True),
        sa.Column("footnote", sa.String(), nullable=True),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.Column("aliases", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brand.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "slug", name="uq_brand_feature_brand_id_slug"),
    )
    op.create_index(op.f("ix_brand_feature_brand_id"), "brand_feature", ["brand_id"], unique=False)
    op.create_index(op.f("ix_brand_feature_is_published"), "brand_feature", ["is_published"], unique=False)
    op.create_index(op.f("ix_brand_feature_slug"), "brand_feature", ["slug"], unique=False)
    op.create_index(op.f("ix_brand_feature_sort_order"), "brand_feature", ["sort_order"], unique=False)
    op.create_index(op.f("ix_brand_feature_title"), "brand_feature", ["title"], unique=False)

    op.create_table(
        "product_series_feature_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("feature_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("title_override", sa.String(), nullable=True),
        sa.Column("text_override", sa.Text(), nullable=True),
        sa.Column("image_url_override", sa.String(), nullable=True),
        sa.Column("icon_override", sa.String(), nullable=True),
        sa.Column("footnote_override", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["feature_id"], ["brand_feature.id"]),
        sa.ForeignKeyConstraint(["series_id"], ["product_series.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("series_id", "feature_id", name="uq_product_series_feature_link"),
    )
    op.create_index(op.f("ix_product_series_feature_link_feature_id"), "product_series_feature_link", ["feature_id"], unique=False)
    op.create_index(op.f("ix_product_series_feature_link_series_id"), "product_series_feature_link", ["series_id"], unique=False)
    op.create_index(op.f("ix_product_series_feature_link_sort_order"), "product_series_feature_link", ["sort_order"], unique=False)

    op.alter_column("brand_feature", "aliases", server_default=None)
    op.alter_column("brand_feature", "is_published", server_default=None)
    op.alter_column("brand_feature", "sort_order", server_default=None)
    op.alter_column("product_series_feature_link", "sort_order", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_product_series_feature_link_sort_order"), table_name="product_series_feature_link")
    op.drop_index(op.f("ix_product_series_feature_link_series_id"), table_name="product_series_feature_link")
    op.drop_index(op.f("ix_product_series_feature_link_feature_id"), table_name="product_series_feature_link")
    op.drop_table("product_series_feature_link")

    op.drop_index(op.f("ix_brand_feature_title"), table_name="brand_feature")
    op.drop_index(op.f("ix_brand_feature_sort_order"), table_name="brand_feature")
    op.drop_index(op.f("ix_brand_feature_slug"), table_name="brand_feature")
    op.drop_index(op.f("ix_brand_feature_is_published"), table_name="brand_feature")
    op.drop_index(op.f("ix_brand_feature_brand_id"), table_name="brand_feature")
    op.drop_table("brand_feature")
