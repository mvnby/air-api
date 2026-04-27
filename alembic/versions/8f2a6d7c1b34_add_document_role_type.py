"""add_document_role_type

Revision ID: 8f2a6d7c1b34
Revises: 6a7b8c9d0e1f
Create Date: 2026-04-27 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy import inspect


revision: str = "8f2a6d7c1b34"
down_revision: Union[str, Sequence[str], None] = "6a7b8c9d0e1f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    order_columns = {column["name"] for column in inspector.get_columns("order")}
    if "document_role_type" not in order_columns:
        with op.batch_alter_table("order", schema=None) as batch_op:
            batch_op.add_column(sa.Column("document_role_type", sa.String(), nullable=True))

    contract_columns = {column["name"] for column in inspector.get_columns("customer_contract")}
    if "document_role_type" not in contract_columns:
        with op.batch_alter_table("customer_contract", schema=None) as batch_op:
            batch_op.add_column(sa.Column("document_role_type", sa.String(), nullable=True))


def downgrade() -> None:
    bind = op.get_bind()
    inspector = inspect(bind)

    contract_columns = {column["name"] for column in inspector.get_columns("customer_contract")}
    if "document_role_type" in contract_columns:
        with op.batch_alter_table("customer_contract", schema=None) as batch_op:
            batch_op.drop_column("document_role_type")

    order_columns = {column["name"] for column in inspector.get_columns("order")}
    if "document_role_type" in order_columns:
        with op.batch_alter_table("order", schema=None) as batch_op:
            batch_op.drop_column("document_role_type")
