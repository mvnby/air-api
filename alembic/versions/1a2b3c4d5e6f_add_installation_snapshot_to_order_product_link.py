"""add_installation_snapshot_to_order_product_link

Revision ID: 1a2b3c4d5e6f
Revises: f37e06766b7c
Create Date: 2026-01-26 23:38:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '1a2b3c4d5e6f'
down_revision = 'f37e06766b7c'
branch_labels = None
depends_on = None


def upgrade():
    from sqlalchemy import inspect
    
    connection = op.get_bind()
    inspector = inspect(connection)
    
    # Get existing columns
    existing_columns = [col['name'] for col in inspector.get_columns('order_product_link')]
    
    # Add installation snapshot fields to order_product_link only if they don't exist
    if 'is_installation_included' not in existing_columns:
        op.add_column('order_product_link', sa.Column('is_installation_included', sa.Boolean(), nullable=False, server_default='false'))
        # Remove server default after adding column
        op.alter_column('order_product_link', 'is_installation_included', server_default=None)
    
    if 'installation_price' not in existing_columns:
        op.add_column('order_product_link', sa.Column('installation_price', sa.Integer(), nullable=False, server_default='0'))
        # Remove server default after adding column
        op.alter_column('order_product_link', 'installation_price', server_default=None)
    
    if 'installation_details' not in existing_columns:
        op.add_column('order_product_link', sa.Column('installation_details', postgresql.JSON(astext_type=sa.Text()), nullable=True))


def downgrade():
    # Remove installation snapshot fields
    op.drop_column('order_product_link', 'installation_details')
    op.drop_column('order_product_link', 'installation_price')
    op.drop_column('order_product_link', 'is_installation_included')
