"""add short and full service description variants

Revision ID: 6e1a3c5d7f90
Revises: 5b9d7e1a2c80
Create Date: 2026-07-16 12:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "6e1a3c5d7f90"
down_revision: Union[str, Sequence[str], None] = "5b9d7e1a2c80"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    tariff_columns = _columns("service_tariff")
    with op.batch_alter_table("service_tariff", schema=None) as batch_op:
        if "short_name" not in tariff_columns:
            batch_op.add_column(sa.Column("short_name", sa.String(), nullable=True))
        if "full_description" not in tariff_columns:
            batch_op.add_column(sa.Column("full_description", sa.Text(), nullable=True))

    if "ix_service_tariff_short_name" not in _indexes("service_tariff"):
        op.create_index(
            "ix_service_tariff_short_name",
            "service_tariff",
            ["short_name"],
            unique=False,
        )

    op.execute(
        sa.text(
            """
            UPDATE service_tariff
            SET short_name = COALESCE(NULLIF(TRIM(short_name), ''), selector_label),
                full_description = COALESCE(
                    NULLIF(TRIM(full_description), ''),
                    NULLIF(TRIM(estimate_template), '')
                )
            """
        )
    )

    item_columns = _columns("service_estimate_item")
    with op.batch_alter_table("service_estimate_item", schema=None) as batch_op:
        if "short_name" not in item_columns:
            batch_op.add_column(sa.Column("short_name", sa.String(), nullable=True))
        if "full_description" not in item_columns:
            batch_op.add_column(sa.Column("full_description", sa.Text(), nullable=True))

    op.execute(
        sa.text(
            """
            UPDATE service_estimate_item
            SET short_name = COALESCE(NULLIF(TRIM(short_name), ''), name)
            """
        )
    )
    op.execute(
        sa.text(
            """
            UPDATE service_estimate_item
            SET full_description = COALESCE(
                NULLIF(TRIM(full_description), ''),
                (
                    SELECT COALESCE(
                        NULLIF(TRIM(service_tariff.full_description), ''),
                        NULLIF(TRIM(service_tariff.estimate_template), '')
                    )
                    FROM service_estimate
                    JOIN service_tariff ON service_tariff.id = service_estimate.tariff_id
                    WHERE service_estimate.id = service_estimate_item.estimate_id
                )
            )
            WHERE source_type = 'base'
            """
        )
    )


def downgrade() -> None:
    item_columns = _columns("service_estimate_item")
    with op.batch_alter_table("service_estimate_item", schema=None) as batch_op:
        if "full_description" in item_columns:
            batch_op.drop_column("full_description")
        if "short_name" in item_columns:
            batch_op.drop_column("short_name")

    if "ix_service_tariff_short_name" in _indexes("service_tariff"):
        op.drop_index("ix_service_tariff_short_name", table_name="service_tariff")
    tariff_columns = _columns("service_tariff")
    with op.batch_alter_table("service_tariff", schema=None) as batch_op:
        if "full_description" in tariff_columns:
            batch_op.drop_column("full_description")
        if "short_name" in tariff_columns:
            batch_op.drop_column("short_name")
