"""Series accessory compatibility with explicit per-model exceptions.

Revision ID: cat20261019acc01
Revises: w20261017pay02
"""

from alembic import op
import sqlalchemy as sa


revision = "cat20261019acc01"
down_revision = "w20261017pay02"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "series_accessory_link",
        sa.Column("series_id", sa.Integer(), nullable=False),
        sa.Column("accessory_product_id", sa.Integer(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["series_id"], ["product_series.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["accessory_product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("series_id", "accessory_product_id"),
        sa.CheckConstraint("sort_order >= 0", name="ck_series_accessory_sort_order"),
    )
    op.create_index("ix_series_accessory_link_accessory_product_id", "series_accessory_link", ["accessory_product_id"])
    op.create_table(
        "product_accessory_override",
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("accessory_product_id", sa.Integer(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["accessory_product_id"], ["product.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("product_id", "accessory_product_id"),
        sa.CheckConstraint("product_id <> accessory_product_id", name="ck_product_accessory_not_self"),
        sa.CheckConstraint("sort_order >= 0", name="ck_product_accessory_sort_order"),
    )
    op.create_index("ix_product_accessory_override_accessory_product_id", "product_accessory_override", ["accessory_product_id"])


def downgrade():
    op.drop_table("product_accessory_override")
    op.drop_table("series_accessory_link")
