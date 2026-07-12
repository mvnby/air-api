"""Baseline for the schema that existed before Alembic was introduced.

The project used SQLModel ``create_all`` and two explicit SQLite-era schema
scripts before revision ``a55c3fc61562``.  The first Alembic revision therefore
contains only a delta and cannot run against an empty database by itself.  This
baseline records that pre-Alembic schema so a fresh PostgreSQL database can
replay the complete, data-preserving migration history.

Revision ID: 000000000001
Revises:
Create Date: 2026-07-13
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "000000000001"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "article",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.Text(), nullable=True),
        sa.Column("content", sa.String(), nullable=False),
        sa.Column("main_image", sa.Text(), nullable=True),
        sa.Column("image_url", sa.String(), nullable=True),
        sa.Column("is_published", sa.Boolean(), server_default=sa.true(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("idx_article_slug", "article", ["slug"], unique=True)

    op.create_table(
        "cart",
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("user_id"),
    )

    op.create_table(
        "customer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("phone", sa.Text(), nullable=False),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("type", sa.Text(), server_default="individual", nullable=True),
        sa.Column("full_legal_name", sa.Text(), nullable=True),
        sa.Column("inn", sa.Text(), nullable=True),
        sa.Column("kpp", sa.Text(), nullable=True),
        sa.Column("legal_address", sa.Text(), nullable=True),
        sa.Column("actual_address", sa.Text(), nullable=True),
        sa.Column("bank_name", sa.Text(), nullable=True),
        sa.Column("bic", sa.Text(), nullable=True),
        sa.Column("iban", sa.Text(), nullable=True),
        sa.Column("signer_position", sa.Text(), server_default="Генерального директора", nullable=True),
        sa.Column("signer_name", sa.Text(), nullable=True),
        sa.Column("acting_basis", sa.Text(), server_default="Устава", nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_inn", "customer", ["inn"], unique=False)
    op.create_index("ix_customer_name", "customer", ["name"], unique=False)
    op.create_index("ix_customer_phone", "customer", ["phone"], unique=False)

    op.create_table(
        "global_config",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("key", sa.String(), nullable=False),
        sa.Column("value", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_global_config_key", "global_config", ["key"], unique=True)

    op.create_table(
        "product",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.Column("old_price", sa.Integer(), nullable=True),
        sa.Column("area", sa.Integer(), nullable=False),
        sa.Column("is_inverter", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("power_cooling", sa.Float(), nullable=True),
        sa.Column("main_image", sa.String(), nullable=True),
        sa.Column("images", sa.JSON(), nullable=True),
        sa.Column("categories", sa.JSON(), nullable=True),
        sa.Column("specs", sa.JSON(), nullable=True),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("source_url", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_product_area", "product", ["area"], unique=False)
    op.create_index("ix_product_source_url", "product", ["source_url"], unique=False)
    op.create_index("ix_product_title", "product", ["title"], unique=False)

    op.create_table(
        "service",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=True),
        sa.Column("base_price", sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_title", "service", ["title"], unique=False)

    # Revision f3f1ac945939 was committed as an empty migration because the
    # application used create_all during that period.  A later data migration
    # reads this table, so the bootstrap baseline must record it explicitly.
    op.create_table(
        "installation_rates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("category", sa.String(), nullable=False),
        sa.Column("power_range", sa.String(), nullable=False, server_default=""),
        sa.Column("base_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("extra_pipe_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("included_pipe_meters", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("is_fixed", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("comment", sa.String(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_installation_rates_category",
        "installation_rates",
        ["category"],
        unique=False,
    )

    op.create_table(
        "tag_group",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("color", sa.String(), server_default="secondary", nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("allow_multiple", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tag_group_slug", "tag_group", ["slug"], unique=True)
    op.create_index("ix_tag_group_title", "tag_group", ["title"], unique=False)

    op.create_table(
        "cartitem",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("cart_user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["cart_user_id"], ["cart.user_id"]),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "favorite",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_favorite_user_id", "favorite", ["user_id"], unique=False)

    op.create_table(
        "order",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("delivery_address", sa.Text(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.Text(), server_default="new", nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_order_user_id", "order", ["user_id"], unique=False)

    op.create_table(
        "tag",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("group_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False),
        sa.Column("is_public", sa.Boolean(), nullable=False),
        sa.Column("is_filter", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("ai_snippet", sa.String(), nullable=True),
        sa.Column("reliability_score", sa.Float(), nullable=True),
        sa.ForeignKeyConstraint(["group_id"], ["tag_group.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tag_slug", "tag", ["slug"], unique=False)
    op.create_index("ix_tag_title", "tag", ["title"], unique=False)

    op.create_table(
        "order_product_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "order_service_link",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("service_id", sa.Integer(), nullable=True),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("price", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["service.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "product_tag_link",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("tag_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["tag_id"], ["tag.id"]),
        sa.PrimaryKeyConstraint("product_id", "tag_id"),
    )


def downgrade() -> None:
    op.drop_table("product_tag_link")
    op.drop_table("order_service_link")
    op.drop_table("order_product_link")
    op.drop_index("ix_tag_title", table_name="tag")
    op.drop_index("ix_tag_slug", table_name="tag")
    op.drop_table("tag")
    op.drop_index("ix_order_user_id", table_name="order")
    op.drop_table("order")
    op.drop_index("ix_favorite_user_id", table_name="favorite")
    op.drop_table("favorite")
    op.drop_table("cartitem")
    op.drop_index("ix_tag_group_title", table_name="tag_group")
    op.drop_index("ix_tag_group_slug", table_name="tag_group")
    op.drop_table("tag_group")
    op.drop_index("ix_service_title", table_name="service")
    op.drop_table("service")
    op.drop_index("ix_installation_rates_category", table_name="installation_rates")
    op.drop_table("installation_rates")
    op.drop_index("ix_product_title", table_name="product")
    op.drop_index("ix_product_source_url", table_name="product")
    op.drop_index("ix_product_area", table_name="product")
    op.drop_table("product")
    op.drop_index("ix_global_config_key", table_name="global_config")
    op.drop_table("global_config")
    op.drop_index("ix_customer_phone", table_name="customer")
    op.drop_index("ix_customer_name", table_name="customer")
    op.drop_index("ix_customer_inn", table_name="customer")
    op.drop_table("customer")
    op.drop_table("cart")
    op.drop_index("idx_article_slug", table_name="article")
    op.drop_table("article")
