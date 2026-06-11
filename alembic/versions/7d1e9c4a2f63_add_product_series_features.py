"""add product series features

Revision ID: 7d1e9c4a2f63
Revises: 4a2b6c8d0e91
Create Date: 2026-06-11 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7d1e9c4a2f63"
down_revision: Union[str, Sequence[str], None] = "4a2b6c8d0e91"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_series",
        sa.Column("features", sa.JSON(), nullable=False, server_default=sa.text("'[]'")),
    )
    op.alter_column("product_series", "features", server_default=None)


def downgrade() -> None:
    op.drop_column("product_series", "features")
