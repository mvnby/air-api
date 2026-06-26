"""add_order_negotiation_workflow_fields

Revision ID: 9f2c8d7e6a51
Revises: 0abf9e6d4c12
Create Date: 2026-06-25 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "9f2c8d7e6a51"
down_revision: Union[str, Sequence[str], None] = "0abf9e6d4c12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _column_names(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    columns = _column_names("order")
    index_names = {idx["name"] for idx in sa.inspect(op.get_bind()).get_indexes("order")}
    with op.batch_alter_table("order", schema=None) as batch_op:
        if "negotiation_status" not in columns:
            batch_op.add_column(sa.Column("negotiation_status", sa.String(), nullable=False, server_default="awaiting_offer"))
        if "negotiation_status_changed_at" not in columns:
            batch_op.add_column(sa.Column("negotiation_status_changed_at", sa.DateTime(), nullable=True))
        if "execution_without_payment" not in columns:
            batch_op.add_column(sa.Column("execution_without_payment", sa.Boolean(), nullable=False, server_default=sa.false()))
        if "execution_without_payment_reason" not in columns:
            batch_op.add_column(sa.Column("execution_without_payment_reason", sa.String(), nullable=True))
        if "status_changed_at" not in columns:
            batch_op.add_column(sa.Column("status_changed_at", sa.DateTime(), nullable=True))

    columns = _column_names("order")
    with op.batch_alter_table("order", schema=None) as batch_op:
        if "negotiation_status" in columns and "ix_order_negotiation_status" not in index_names:
            batch_op.create_index("ix_order_negotiation_status", ["negotiation_status"])
        if "execution_without_payment" in columns and "ix_order_execution_without_payment" not in index_names:
            batch_op.create_index("ix_order_execution_without_payment", ["execution_without_payment"])

    op.execute(
        """
        UPDATE "order"
        SET
            status_changed_at = COALESCE(status_changed_at, updated_at, created_at),
            negotiation_status_changed_at = COALESCE(negotiation_status_changed_at, updated_at, created_at),
            negotiation_status = CASE
                WHEN proposal_status = 'sent' THEN 'proposal_sent'
                WHEN proposal_status = 'approved' AND COALESCE(is_paid, false) = false THEN 'awaiting_payment'
                WHEN COALESCE(measurement_required, false) = true THEN 'awaiting_visit'
                ELSE COALESCE(NULLIF(negotiation_status, ''), 'awaiting_offer')
            END
        """
    )


def downgrade() -> None:
    columns = _column_names("order")
    index_names = {idx["name"] for idx in sa.inspect(op.get_bind()).get_indexes("order")}
    with op.batch_alter_table("order", schema=None) as batch_op:
        if "ix_order_execution_without_payment" in index_names:
            batch_op.drop_index("ix_order_execution_without_payment")
        if "ix_order_negotiation_status" in index_names:
            batch_op.drop_index("ix_order_negotiation_status")
        if "status_changed_at" in columns:
            batch_op.drop_column("status_changed_at")
        if "execution_without_payment_reason" in columns:
            batch_op.drop_column("execution_without_payment_reason")
        if "execution_without_payment" in columns:
            batch_op.drop_column("execution_without_payment")
        if "negotiation_status_changed_at" in columns:
            batch_op.drop_column("negotiation_status_changed_at")
        if "negotiation_status" in columns:
            batch_op.drop_column("negotiation_status")
