"""make_service_id_nullable_in_order_service_link

Revision ID: 88e5255e2d73
Revises: 42008a09b296
Create Date: 2026-01-26 22:32:05.219163

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '88e5255e2d73'
down_revision: Union[str, Sequence[str], None] = '42008a09b296'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Make service_id nullable in order_service_link table."""
    from sqlalchemy import inspect
    
    connection = op.get_bind()
    inspector = inspect(connection)
    
    # Get existing constraints
    constraints = inspector.get_foreign_keys('order_service_link')
    fk_exists = any(c['name'] == 'order_service_link_service_id_fkey' for c in constraints)
    
    # Drop the foreign key constraint first (if it exists)
    if fk_exists:
        op.drop_constraint('order_service_link_service_id_fkey', 'order_service_link', type_='foreignkey')
    
    # Alter column to nullable
    op.alter_column('order_service_link', 'service_id',
                    existing_type=sa.INTEGER(),
                    nullable=True)
    
    # Recreate foreign key with ondelete SET NULL (if it was dropped or doesn't exist)
    if fk_exists or not any(c['name'] == 'order_service_link_service_id_fkey' for c in inspector.get_foreign_keys('order_service_link')):
        op.create_foreign_key(
            'order_service_link_service_id_fkey',
            'order_service_link', 'service',
            ['service_id'], ['id'],
            ondelete='SET NULL'
        )


def downgrade() -> None:
    """Revert service_id to not nullable."""
    # Drop the altered foreign key
    op.drop_constraint('order_service_link_service_id_fkey', 'order_service_link', type_='foreignkey')
    
    # Make column NOT NULL again
    op.alter_column('order_service_link', 'service_id',
                    existing_type=sa.INTEGER(),
                    nullable=False)
    
    # Recreate original foreign key
    op.create_foreign_key(
        'order_service_link_service_id_fkey',
        'order_service_link', 'service',
        ['service_id'], ['id']
    )
