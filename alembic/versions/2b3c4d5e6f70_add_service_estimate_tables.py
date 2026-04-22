"""add service estimate tables

Revision ID: 2b3c4d5e6f70
Revises: 1f2e3d4c5b6a
Create Date: 2026-04-21 10:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2b3c4d5e6f70"
down_revision: Union[str, Sequence[str], None] = "1f2e3d4c5b6a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "service_estimate",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("comment", sa.String(), nullable=True),
        sa.Column("service_kind", sa.String(), nullable=False, server_default=sa.text("'install'")),
        sa.Column("currency", sa.String(), nullable=False, server_default=sa.text("'BYN'")),
        sa.Column("subtotal", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("discount_amount", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("total", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("calculation_payload", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default=sa.text("'draft'")),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_estimate_customer_id", "service_estimate", ["customer_id"], unique=False)
    op.create_index("ix_service_estimate_service_kind", "service_estimate", ["service_kind"], unique=False)
    op.create_index("ix_service_estimate_status", "service_estimate", ["status"], unique=False)
    op.create_index("ix_service_estimate_created_by", "service_estimate", ["created_by"], unique=False)

    op.create_table(
        "service_estimate_item",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("estimate_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sa.String(), nullable=False, server_default=sa.text("'base'")),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("qty", sa.Float(), nullable=False, server_default=sa.text("1.0")),
        sa.Column("unit", sa.String(), nullable=False, server_default=sa.text("'шт'")),
        sa.Column("unit_price", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("line_total", sa.Float(), nullable=False, server_default=sa.text("0.0")),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.ForeignKeyConstraint(["estimate_id"], ["service_estimate.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_estimate_item_estimate_id", "service_estimate_item", ["estimate_id"], unique=False)
    op.create_index("ix_service_estimate_item_source_type", "service_estimate_item", ["source_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_service_estimate_item_source_type", table_name="service_estimate_item")
    op.drop_index("ix_service_estimate_item_estimate_id", table_name="service_estimate_item")
    op.drop_table("service_estimate_item")

    op.drop_index("ix_service_estimate_created_by", table_name="service_estimate")
    op.drop_index("ix_service_estimate_status", table_name="service_estimate")
    op.drop_index("ix_service_estimate_service_kind", table_name="service_estimate")
    op.drop_index("ix_service_estimate_customer_id", table_name="service_estimate")
    op.drop_table("service_estimate")
