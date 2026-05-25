"""add_order_product_logistics_components

Revision ID: 9a3f6b8c1d2e
Revises: 8b61a5d4c3e2
Create Date: 2026-05-25 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "9a3f6b8c1d2e"
down_revision: Union[str, Sequence[str], None] = "8b61a5d4c3e2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if "logistics_components" in _columns("order_product_link"):
        return
    with op.batch_alter_table("order_product_link", schema=None) as batch_op:
        batch_op.add_column(sa.Column("logistics_components", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("order_product_link", schema=None) as batch_op:
        batch_op.drop_column("logistics_components")
