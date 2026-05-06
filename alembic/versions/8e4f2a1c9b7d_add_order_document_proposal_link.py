"""Add order document proposal link

Revision ID: 8e4f2a1c9b7d
Revises: 7c2d9e1f4a6b
Create Date: 2026-05-06 20:50:00.000000

"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "8e4f2a1c9b7d"
down_revision: Union[str, Sequence[str], None] = "7c2d9e1f4a6b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _columns(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {column["name"] for column in inspector.get_columns(table_name)}


def _indexes(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {index["name"] for index in inspector.get_indexes(table_name)}


def _foreign_keys(table_name: str) -> set[str]:
    inspector = sa.inspect(op.get_bind())
    return {fk["name"] for fk in inspector.get_foreign_keys(table_name) if fk.get("name")}


def upgrade() -> None:
    if "proposal_id" not in _columns("order_document"):
        with op.batch_alter_table("order_document", schema=None) as batch_op:
            batch_op.add_column(sa.Column("proposal_id", sa.Integer(), nullable=True))

    if "ix_order_document_proposal_id" not in _indexes("order_document"):
        op.create_index("ix_order_document_proposal_id", "order_document", ["proposal_id"])

    if "fk_order_document_proposal_id_order_proposal" not in _foreign_keys("order_document"):
        with op.batch_alter_table("order_document", schema=None) as batch_op:
            batch_op.create_foreign_key(
                "fk_order_document_proposal_id_order_proposal",
                "order_proposal",
                ["proposal_id"],
                ["id"],
            )


def downgrade() -> None:
    with op.batch_alter_table("order_document", schema=None) as batch_op:
        batch_op.drop_constraint(batch_op.f("fk_order_document_proposal_id_order_proposal"), type_="foreignkey")
        batch_op.drop_index(batch_op.f("ix_order_document_proposal_id"))
        batch_op.drop_column("proposal_id")
