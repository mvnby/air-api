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


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _foreign_key_names(table_name: str) -> set[str]:
    return {fk["name"] for fk in sa.inspect(op.get_bind()).get_foreign_keys(table_name) if fk.get("name")}


def upgrade() -> None:
    columns = _column_names("order_document")
    if "scope_customer_branch_id" not in columns:
        op.add_column("order_document", sa.Column("scope_customer_branch_id", sa.Integer(), nullable=True))
    if "scope_title" not in columns:
        op.add_column("order_document", sa.Column("scope_title", sa.String(), nullable=True))
    if "scope_address" not in columns:
        op.add_column("order_document", sa.Column("scope_address", sa.String(), nullable=True))
    if "scope_meta" not in columns:
        op.add_column("order_document", sa.Column("scope_meta", sa.JSON(), nullable=True))
    if "ix_order_document_scope_customer_branch_id" not in _index_names("order_document"):
        op.create_index(
            "ix_order_document_scope_customer_branch_id",
            "order_document",
            ["scope_customer_branch_id"],
        )
    if "fk_order_document_scope_customer_branch_id" not in _foreign_key_names("order_document"):
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
