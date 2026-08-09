"""add brand featured series contract

Revision ID: f4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-08-09
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f4b5c6d7e8f9"
down_revision: str | None = "f3a4b5c6d7e8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("brand", sa.Column("short_description", sa.Text(), nullable=True))
    op.add_column(
        "product_series",
        sa.Column(
            "is_featured",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_product_series_brand_featured_public_sort",
        "product_series",
        ["brand_id", "is_featured", "is_published", "sort_order", "id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_product_series_brand_featured_public_sort",
        table_name="product_series",
    )
    op.drop_column("product_series", "is_featured")
    op.drop_column("brand", "short_description")
