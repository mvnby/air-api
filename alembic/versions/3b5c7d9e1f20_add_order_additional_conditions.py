"""add order additional conditions

Revision ID: 3b5c7d9e1f20
Revises: 0d4f7a9c3e21
Create Date: 2026-05-13 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "3b5c7d9e1f20"
down_revision: Union[str, Sequence[str], None] = "0d4f7a9c3e21"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def upgrade() -> None:
    if "additional_conditions" not in _columns("order"):
        with op.batch_alter_table("order", schema=None) as batch_op:
            batch_op.add_column(sa.Column("additional_conditions", sa.Text(), nullable=True))


def downgrade() -> None:
    if "additional_conditions" in _columns("order"):
        with op.batch_alter_table("order", schema=None) as batch_op:
            batch_op.drop_column("additional_conditions")
