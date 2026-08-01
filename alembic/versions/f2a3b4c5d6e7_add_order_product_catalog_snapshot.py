"""Add immutable public catalog title and currency snapshots.

Revision ID: f2a3b4c5d6e7
Revises: ab02c3d4e5f6
Create Date: 2026-08-01
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "f2a3b4c5d6e7"
down_revision: str | Sequence[str] | None = "ab02c3d4e5f6"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable expansion keeps historical lines honest: only newly captured
    # links can claim a title and currency fixed at creation time.
    op.add_column(
        "order_product_link",
        sa.Column("title_snapshot", sa.Text(), nullable=True),
    )
    op.add_column(
        "order_product_link",
        sa.Column("currency_snapshot", sa.String(length=3), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_product_link", "currency_snapshot")
    op.drop_column("order_product_link", "title_snapshot")
