"""add order workflow type

Revision ID: 6b8d1f4c2a90
Revises: 5a7c9d2e1f03
Create Date: 2026-05-14 09:20:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "6b8d1f4c2a90"
down_revision: Union[str, Sequence[str], None] = "5a7c9d2e1f03"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    if "workflow_type" not in _columns("order"):
        with op.batch_alter_table("order", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column(
                    "workflow_type",
                    sa.String(),
                    nullable=False,
                    server_default=sa.text("'sales_installation'"),
                )
            )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE "order"
            SET workflow_type = CASE
                WHEN technical_meta ->> 'service_type' = 'repair'
                    OR lower(coalesce(title, '')) LIKE '%ремонт%'
                    THEN 'repair'
                WHEN technical_meta ->> 'service_type' = 'maintenance'
                    OR lower(coalesce(title, '')) LIKE '%обслуж%'
                    THEN 'maintenance'
                WHEN technical_meta ->> 'service_type' IN ('install_only', 'pre_install', 'dismantling')
                    OR lower(coalesce(title, '')) LIKE '%демонтаж%'
                    OR lower(coalesce(title, '')) LIKE '%монтаж%'
                    OR lower(coalesce(title, '')) LIKE '%заклад%'
                    THEN 'service_work'
                ELSE 'sales_installation'
            END
            WHERE workflow_type IS NULL OR workflow_type = 'sales_installation'
            """
        )
    )

    if "ix_order_workflow_type" not in _indexes("order"):
        with op.batch_alter_table("order", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_order_workflow_type"), ["workflow_type"], unique=False)


def downgrade() -> None:
    if "ix_order_workflow_type" in _indexes("order"):
        with op.batch_alter_table("order", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_order_workflow_type"))
    if "workflow_type" in _columns("order"):
        with op.batch_alter_table("order", schema=None) as batch_op:
            batch_op.drop_column("workflow_type")
