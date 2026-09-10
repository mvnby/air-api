"""Add a client-facing description to order product lines.

Revision ID: d43f9a0c6e84
Revises: c42e8f9b5d73
Create Date: 2026-09-10
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "d43f9a0c6e84"
down_revision: str | Sequence[str] | None = "c42e8f9b5d73"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "order_product_link",
        sa.Column("client_description", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("order_product_link", "client_description")
