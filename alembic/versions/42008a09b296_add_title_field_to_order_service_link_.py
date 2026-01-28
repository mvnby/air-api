"""add title field to order_service_link for custom service names

Revision ID: 42008a09b296
Revises: 1a2b3c4d5e6f
Create Date: 2026-01-26 22:22:34.891527

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '42008a09b296'
down_revision: Union[str, Sequence[str], None] = '1a2b3c4d5e6f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    from sqlalchemy import inspect
    
    connection = op.get_bind()
    inspector = inspect(connection)
    existing_columns = [col['name'] for col in inspector.get_columns('order_service_link')]
    
    # Add title column to order_service_link only if it doesn't exist
    if 'title' not in existing_columns:
        op.add_column('order_service_link', sa.Column('title', sa.String(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    # Remove title column from order_service_link
    op.drop_column('order_service_link', 'title')
