"""add_order_auto_execution_on_payment

Revision ID: a0b1c2d3e4f5
Revises: 9f2c8d7e6a51
Create Date: 2026-06-26 14:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "a0b1c2d3e4f5"
down_revision: Union[str, Sequence[str], None] = "9f2c8d7e6a51"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    columns = _column_names("order")
    index_names = _index_names("order")
    with op.batch_alter_table("order", schema=None) as batch_op:
        if "auto_execution_on_payment" not in columns:
            batch_op.add_column(
                sa.Column("auto_execution_on_payment", sa.Boolean(), nullable=False, server_default=sa.false())
            )
        if "ix_order_auto_execution_on_payment" not in index_names:
            batch_op.create_index("ix_order_auto_execution_on_payment", ["auto_execution_on_payment"])


def downgrade() -> None:
    columns = _column_names("order")
    index_names = _index_names("order")
    with op.batch_alter_table("order", schema=None) as batch_op:
        if "ix_order_auto_execution_on_payment" in index_names:
            batch_op.drop_index("ix_order_auto_execution_on_payment")
        if "auto_execution_on_payment" in columns:
            batch_op.drop_column("auto_execution_on_payment")
