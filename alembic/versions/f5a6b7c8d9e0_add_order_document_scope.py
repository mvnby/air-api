"""Add order document scope

Revision ID: f5a6b7c8d9e0
Revises: e4f5a6b7c8d9
Create Date: 2026-06-22 00:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f5a6b7c8d9e0"
down_revision: Union[str, Sequence[str], None] = "e4f5a6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("order_document", sa.Column("scope_customer_branch_id", sa.Integer(), nullable=True))
    op.add_column("order_document", sa.Column("scope_title", sa.String(), nullable=True))
    op.add_column("order_document", sa.Column("scope_address", sa.String(), nullable=True))
    op.add_column("order_document", sa.Column("scope_meta", sa.JSON(), nullable=True))
    op.create_index(
        "ix_order_document_scope_customer_branch_id",
        "order_document",
        ["scope_customer_branch_id"],
    )
    op.create_foreign_key(
        "fk_order_document_scope_customer_branch_id",
        "order_document",
        "customer_branches",
        ["scope_customer_branch_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_order_document_scope_customer_branch_id", "order_document", type_="foreignkey")
    op.drop_index("ix_order_document_scope_customer_branch_id", table_name="order_document")
    op.drop_column("order_document", "scope_meta")
    op.drop_column("order_document", "scope_address")
    op.drop_column("order_document", "scope_title")
    op.drop_column("order_document", "scope_customer_branch_id")
