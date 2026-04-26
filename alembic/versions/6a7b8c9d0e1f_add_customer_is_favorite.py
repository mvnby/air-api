"""add_customer_is_favorite

Revision ID: 6a7b8c9d0e1f
Revises: 9c2d1f8a7b64
Create Date: 2026-04-27 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "6a7b8c9d0e1f"
down_revision: Union[str, Sequence[str], None] = "9c2d1f8a7b64"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("customer", schema=None) as batch_op:
        batch_op.add_column(
            sa.Column("is_favorite", sa.Boolean(), nullable=False, server_default=sa.text("false"))
        )
        batch_op.create_index(batch_op.f("ix_customer_is_favorite"), ["is_favorite"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("customer", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_customer_is_favorite"))
        batch_op.drop_column("is_favorite")
