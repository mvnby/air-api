"""Link follow-up email leads to existing orders without losing the source.

Revision ID: a9d1e2f3b4c5
Revises: f8e1d2c3b4a5
"""

import sqlalchemy as sa
from alembic import op


revision = "a9d1e2f3b4c5"
down_revision = "f8e1d2c3b4a5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order", sa.Column("linked_order_id", sa.Integer(), nullable=True))
    op.add_column("order", sa.Column("linked_at", sa.DateTime(), nullable=True))
    op.add_column("order", sa.Column("linked_by", sa.String(length=120), nullable=True))
    op.create_index("ix_order_linked_order_id", "order", ["linked_order_id"])
    op.create_foreign_key(
        "fk_order_linked_target_same_scope",
        "order",
        "order",
        ["linked_order_id", "tenant_id", "storefront_id"],
        ["id", "tenant_id", "storefront_id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        "ck_order_linked_target_not_self",
        "order",
        "linked_order_id IS NULL OR linked_order_id <> id",
    )
    op.add_column(
        "order_attachment_link",
        sa.Column("origin_order_id", sa.Integer(), nullable=True),
    )
    op.create_index(
        "ix_order_attachment_link_origin_order_id",
        "order_attachment_link",
        ["origin_order_id"],
    )
    op.create_foreign_key(
        "fk_order_attachment_link_origin_order",
        "order_attachment_link",
        "order",
        ["origin_order_id"],
        ["id"],
        ondelete="RESTRICT",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_order_attachment_link_origin_order", "order_attachment_link", type_="foreignkey"
    )
    op.drop_index("ix_order_attachment_link_origin_order_id", table_name="order_attachment_link")
    op.drop_column("order_attachment_link", "origin_order_id")
    op.drop_constraint("ck_order_linked_target_not_self", "order", type_="check")
    op.drop_constraint("fk_order_linked_target_same_scope", "order", type_="foreignkey")
    op.drop_index("ix_order_linked_order_id", table_name="order")
    op.drop_column("order", "linked_by")
    op.drop_column("order", "linked_at")
    op.drop_column("order", "linked_order_id")
