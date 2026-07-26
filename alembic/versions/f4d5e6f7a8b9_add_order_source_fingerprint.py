"""add order source fingerprint

Revision ID: f4d5e6f7a8b9
Revises: f3c4d5e6f7a8
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "f4d5e6f7a8b9"
down_revision: str | None = "f3c4d5e6f7a8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "order",
        sa.Column("source_fingerprint", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_order_source_fingerprint",
        "order",
        ["source_fingerprint"],
        unique=True,
        postgresql_where=sa.text("source_fingerprint IS NOT NULL"),
        sqlite_where=sa.text("source_fingerprint IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("uq_order_source_fingerprint", table_name="order")
    op.drop_column("order", "source_fingerprint")
