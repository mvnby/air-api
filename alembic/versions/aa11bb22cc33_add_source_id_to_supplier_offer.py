"""add source_id to supplier_offer

Revision ID: aa11bb22cc33
Revises: e8f9a0b1c2d3
Create Date: 2026-02-28 01:58:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "aa11bb22cc33"
down_revision: Union[str, Sequence[str], None] = "e8f9a0b1c2d3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("supplier_offer", sa.Column("source_id", sa.Integer(), nullable=True))
    op.create_index("ix_supplier_offer_source_id", "supplier_offer", ["source_id"], unique=False)
    op.create_foreign_key(
        "fk_supplier_offer_source_id",
        "supplier_offer",
        "supplier_price_source",
        ["source_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_supplier_offer_source_id", "supplier_offer", type_="foreignkey")
    op.drop_index("ix_supplier_offer_source_id", table_name="supplier_offer")
    op.drop_column("supplier_offer", "source_id")
