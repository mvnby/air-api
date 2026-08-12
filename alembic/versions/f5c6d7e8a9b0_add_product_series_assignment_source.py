"""add product series assignment provenance

Revision ID: f5c6d7e8a9b0
Revises: f4b5c6d7e8f9
Create Date: 2026-08-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f5c6d7e8a9b0"
down_revision: str | None = "f4b5c6d7e8f9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "product",
        sa.Column(
            "series_assignment_source",
            sa.String(length=16),
            server_default="derived",
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_product_series_assignment_source",
        "product",
        "series_assignment_source IN ('manual', 'derived')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_product_series_assignment_source",
        "product",
        type_="check",
    )
    op.drop_column("product", "series_assignment_source")
