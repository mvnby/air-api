"""add_order_execution_workflow_status

Revision ID: b1c2d3e4f5a6
Revises: a0b1c2d3e4f5
Create Date: 2026-06-26 17:30:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "b1c2d3e4f5a6"
down_revision: Union[str, Sequence[str], None] = "a0b1c2d3e4f5"
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
        if "execution_status" not in columns:
            batch_op.add_column(
                sa.Column("execution_status", sa.String(), nullable=False, server_default="needs_schedule")
            )
        if "execution_status_changed_at" not in columns:
            batch_op.add_column(sa.Column("execution_status_changed_at", sa.DateTime(), nullable=True))
        if "auto_close_on_payment" not in columns:
            batch_op.add_column(sa.Column("auto_close_on_payment", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "ix_order_execution_status" not in index_names:
            batch_op.create_index("ix_order_execution_status", ["execution_status"])
        if "ix_order_auto_close_on_payment" not in index_names:
            batch_op.create_index("ix_order_auto_close_on_payment", ["auto_close_on_payment"])

    op.execute(
        """
        UPDATE "order"
        SET
            execution_status = CASE
                WHEN status = 'execution' AND installation_date IS NOT NULL THEN 'scheduled'
                WHEN status = 'execution' THEN COALESCE(NULLIF(execution_status, ''), 'needs_schedule')
                ELSE COALESCE(NULLIF(execution_status, ''), 'needs_schedule')
            END,
            execution_status_changed_at = CASE
                WHEN status = 'execution'
                THEN COALESCE(execution_status_changed_at, status_changed_at, updated_at, created_at)
                ELSE execution_status_changed_at
            END
        """
    )


def downgrade() -> None:
    columns = _column_names("order")
    index_names = _index_names("order")
    with op.batch_alter_table("order", schema=None) as batch_op:
        if "ix_order_execution_status" in index_names:
            batch_op.drop_index("ix_order_execution_status")
        if "ix_order_auto_close_on_payment" in index_names:
            batch_op.drop_index("ix_order_auto_close_on_payment")
        if "auto_close_on_payment" in columns:
            batch_op.drop_column("auto_close_on_payment")
        if "execution_status_changed_at" in columns:
            batch_op.drop_column("execution_status_changed_at")
        if "execution_status" in columns:
            batch_op.drop_column("execution_status")
