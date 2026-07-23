"""add product collection rules

Revision ID: f3c4d5e6f7a8
Revises: f2b3c4d5e6f7
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f3c4d5e6f7a8"
down_revision: str | None = "f2b3c4d5e6f7"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product_collection",
        sa.Column(
            "sort_mode",
            sa.String(length=32),
            nullable=False,
            server_default="recommended",
        ),
    )
    op.add_column(
        "product_collection",
        sa.Column(
            "rule_config",
            sa.JSON(),
            nullable=False,
            server_default=sa.text("'{}'"),
        ),
    )
    op.create_check_constraint(
        "ck_product_collection_sort_mode",
        "product_collection",
        "sort_mode IN ('recommended', 'price_asc', 'price_desc', 'area_asc', 'area_desc', 'newest')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_product_collection_sort_mode",
        "product_collection",
        type_="check",
    )
    op.drop_column("product_collection", "rule_config")
    op.drop_column("product_collection", "sort_mode")
