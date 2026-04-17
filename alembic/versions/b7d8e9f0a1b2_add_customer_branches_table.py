"""add_customer_branches_table

Revision ID: b7d8e9f0a1b2
Revises: c8f4b0d9e321
Create Date: 2026-04-17 09:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "b7d8e9f0a1b2"
down_revision: Union[str, Sequence[str], None] = "c8f4b0d9e321"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "customer_branches",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=True),
        sa.Column("delivery_address", sa.String(), nullable=False),
        sa.Column("contact_name", sa.String(), nullable=True),
        sa.Column("contact_phone", sa.String(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_customer_branches_customer_id", "customer_branches", ["customer_id"], unique=False)
    op.create_index("ix_customer_branches_is_default", "customer_branches", ["is_default"], unique=False)

    op.add_column("order", sa.Column("customer_branch_id", sa.Integer(), nullable=True))
    op.create_index("ix_order_customer_branch_id", "order", ["customer_branch_id"], unique=False)
    op.create_foreign_key(
        "fk_order_customer_branch_id_customer_branches",
        "order",
        "customer_branches",
        ["customer_branch_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_order_customer_branch_id_customer_branches", "order", type_="foreignkey")
    op.drop_index("ix_order_customer_branch_id", table_name="order")
    op.drop_column("order", "customer_branch_id")

    op.drop_index("ix_customer_branches_is_default", table_name="customer_branches")
    op.drop_index("ix_customer_branches_customer_id", table_name="customer_branches")
    op.drop_table("customer_branches")
