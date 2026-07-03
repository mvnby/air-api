"""Add supplier source URL fields."""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "e5f6a7b8c9d1"
down_revision: Union[str, Sequence[str], None] = "d2e3f4a5b6c7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("supplier_price_source", sa.Column("col_source_url", sa.String(), nullable=True))
    op.add_column("supplier_offer", sa.Column("source_url", sa.String(), nullable=True))
    op.create_index("ix_supplier_offer_source_url", "supplier_offer", ["source_url"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_supplier_offer_source_url", table_name="supplier_offer")
    op.drop_column("supplier_offer", "source_url")
    op.drop_column("supplier_price_source", "col_source_url")
