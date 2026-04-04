"""add_brand_and_series_models

Revision ID: c8f4b0d9e321
Revises: a6fedc10e8ba
Create Date: 2026-04-04 16:25:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c8f4b0d9e321"
down_revision: Union[str, Sequence[str], None] = "a6fedc10e8ba"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "brand",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("logo_url", sa.String(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_brand_title", "brand", ["title"], unique=False)
    op.create_index("ix_brand_slug", "brand", ["slug"], unique=True)
    op.create_index("ix_brand_is_published", "brand", ["is_published"], unique=False)

    op.create_table(
        "product_series",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("brand_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("hero_image", sa.String(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["brand_id"], ["brand.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("brand_id", "slug", name="uq_product_series_brand_id_slug"),
    )
    op.create_index("ix_product_series_title", "product_series", ["title"], unique=False)
    op.create_index("ix_product_series_slug", "product_series", ["slug"], unique=False)
    op.create_index("ix_product_series_brand_id", "product_series", ["brand_id"], unique=False)
    op.create_index("ix_product_series_is_published", "product_series", ["is_published"], unique=False)

    op.add_column("product", sa.Column("brand_id", sa.Integer(), nullable=True))
    op.add_column("product", sa.Column("series_id", sa.Integer(), nullable=True))
    op.create_index("ix_product_brand_id", "product", ["brand_id"], unique=False)
    op.create_index("ix_product_series_id", "product", ["series_id"], unique=False)
    op.create_foreign_key(
        "fk_product_brand_id_brand",
        "product",
        "brand",
        ["brand_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_product_series_id_product_series",
        "product",
        "product_series",
        ["series_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_product_series_id_product_series", "product", type_="foreignkey")
    op.drop_constraint("fk_product_brand_id_brand", "product", type_="foreignkey")
    op.drop_index("ix_product_series_id", table_name="product")
    op.drop_index("ix_product_brand_id", table_name="product")
    op.drop_column("product", "series_id")
    op.drop_column("product", "brand_id")

    op.drop_index("ix_product_series_is_published", table_name="product_series")
    op.drop_index("ix_product_series_brand_id", table_name="product_series")
    op.drop_index("ix_product_series_slug", table_name="product_series")
    op.drop_index("ix_product_series_title", table_name="product_series")
    op.drop_table("product_series")

    op.drop_index("ix_brand_is_published", table_name="brand")
    op.drop_index("ix_brand_slug", table_name="brand")
    op.drop_index("ix_brand_title", table_name="brand")
    op.drop_table("brand")
