"""Add durable manager override for a product's catalog category.

Revision ID: e55b1c2d3e4f
Revises: e54a0b1d7f95
"""

from alembic import op
import sqlalchemy as sa


revision = "e55b1c2d3e4f"
down_revision = "e54a0b1d7f95"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "product",
        sa.Column("catalog_category_override", sa.String(length=32), nullable=True),
    )
    op.create_check_constraint(
        "ck_product_catalog_category_override",
        "product",
        "catalog_category_override IS NULL OR catalog_category_override IN "
        "('cat-household', 'cat-multi', 'cat-industrial')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_product_catalog_category_override",
        "product",
        type_="check",
    )
    op.drop_column("product", "catalog_category_override")
