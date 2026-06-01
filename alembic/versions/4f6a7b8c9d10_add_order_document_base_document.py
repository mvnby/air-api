"""Add order document base links

Revision ID: 4f6a7b8c9d10
Revises: a4e5f6b7c8d9
Create Date: 2026-06-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "4f6a7b8c9d10"
down_revision: Union[str, Sequence[str], None] = "a4e5f6b7c8d9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _foreign_keys(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk.get("name")}


def upgrade() -> None:
    columns = _columns("order_document")
    if "base_document_id" not in columns:
        with op.batch_alter_table("order_document", schema=None) as batch_op:
            batch_op.add_column(sa.Column("base_document_id", sa.Integer(), nullable=True))
    if "base_customer_contract_id" not in columns:
        with op.batch_alter_table("order_document", schema=None) as batch_op:
            batch_op.add_column(sa.Column("base_customer_contract_id", sa.Integer(), nullable=True))

    if "ix_order_document_base_document_id" not in _indexes("order_document"):
        op.create_index("ix_order_document_base_document_id", "order_document", ["base_document_id"])
    if "ix_order_document_base_customer_contract_id" not in _indexes("order_document"):
        op.create_index(
            "ix_order_document_base_customer_contract_id",
            "order_document",
            ["base_customer_contract_id"],
        )

    if "fk_order_document_base_document_id_order_document" not in _foreign_keys("order_document"):
        with op.batch_alter_table("order_document", schema=None) as batch_op:
            batch_op.create_foreign_key(
                "fk_order_document_base_document_id_order_document",
                "order_document",
                ["base_document_id"],
                ["id"],
            )
    if "fk_order_document_base_customer_contract_id_customer_contract" not in _foreign_keys("order_document"):
        with op.batch_alter_table("order_document", schema=None) as batch_op:
            batch_op.create_foreign_key(
                "fk_order_document_base_customer_contract_id_customer_contract",
                "customer_contract",
                ["base_customer_contract_id"],
                ["id"],
            )


def downgrade() -> None:
    with op.batch_alter_table("order_document", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_order_document_base_customer_contract_id_customer_contract"), type_="foreignkey")
        batch_op.drop_constraint(batch_op.f("fk_order_document_base_document_id_order_document"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_order_document_base_customer_contract_id"))
        batch_op.drop_index(batch_op.f("ix_order_document_base_document_id"))
        batch_op.drop_column("base_customer_contract_id")
        batch_op.drop_column("base_document_id")
