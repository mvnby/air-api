"""Add source lineage to product image variants.

Revision ID: a7c8d9e0f1b2
Revises: f6b2a4d8e1c3
"""

from collections.abc import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa


revision: str = "a7c8d9e0f1b2"
down_revision: Union[str, Sequence[str], None] = "f6b2a4d8e1c3"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "product_image_variant",
        sa.Column("source_url", sa.String(length=1000), nullable=True),
    )
    op.add_column(
        "product_image_variant",
        sa.Column("source_content_hash", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("product_image_variant", "source_content_hash")
    op.drop_column("product_image_variant", "source_url")
