"""add favorite tariff rules

Revision ID: 4d6e8f0a2b31
Revises: 3b5c7d9e1f20
Create Date: 2026-05-13 23:45:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "4d6e8f0a2b31"
down_revision: Union[str, Sequence[str], None] = "3b5c7d9e1f20"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def upgrade() -> None:
    if "is_favorite" not in _columns("service_tariff_rule"):
        with op.batch_alter_table("service_tariff_rule", schema=None) as batch_op:
            batch_op.add_column(
                sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("false"))
            )
    if "ix_service_tariff_rule_is_favorite" not in _indexes("service_tariff_rule"):
        with op.batch_alter_table("service_tariff_rule", schema=None) as batch_op:
            batch_op.create_index(batch_op.f("ix_service_tariff_rule_is_favorite"), ["is_favorite"], unique=False)


def downgrade() -> None:
    if "ix_service_tariff_rule_is_favorite" in _indexes("service_tariff_rule"):
        with op.batch_alter_table("service_tariff_rule", schema=None) as batch_op:
            batch_op.drop_index(batch_op.f("ix_service_tariff_rule_is_favorite"))
    if "is_favorite" in _columns("service_tariff_rule"):
        with op.batch_alter_table("service_tariff_rule", schema=None) as batch_op:
            batch_op.drop_column("is_favorite")
