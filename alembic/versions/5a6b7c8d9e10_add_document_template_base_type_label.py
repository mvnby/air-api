"""Add document template base type label

Revision ID: 5a6b7c8d9e10
Revises: 4f6a7b8c9d10
Create Date: 2026-06-01 00:00:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "5a6b7c8d9e10"
down_revision: Union[str, Sequence[str], None] = "4f6a7b8c9d10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    if "base_document_type_label" not in _columns("document_template"):
        with op.batch_alter_table("document_template", schema=None) as batch_op:
            batch_op.add_column(sa.Column("base_document_type_label", sa.String(), nullable=True))


def downgrade() -> None:
    if "base_document_type_label" in _columns("document_template"):
        with op.batch_alter_table("document_template", schema=None) as batch_op:
            batch_op.drop_column("base_document_type_label")
