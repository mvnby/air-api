"""Add standalone maintenance observations and photo links

Revision ID: f11b3c4d5e6f
Revises: f10a2b3c4d5e
Create Date: 2026-10-07 18:42:47.994173

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f11b3c4d5e6f'
down_revision: Union[str, Sequence[str], None] = 'f10a2b3c4d5e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('maintenance_observation',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tenant_id', sa.Integer(), nullable=False),
    sa.Column('storefront_id', sa.Integer(), nullable=False),
    sa.Column('source_order_id', sa.Integer(), nullable=False),
    sa.Column('customer_id', sa.Integer(), nullable=False),
    sa.Column('customer_branch_id', sa.Integer(), nullable=True),
    sa.Column('equipment_id', sa.Integer(), nullable=True),
    sa.Column('command_key', sa.String(length=36), nullable=False),
    sa.Column('command_hash', sa.String(length=64), nullable=False),
    sa.Column('origin', sa.String(length=64), nullable=False),
    sa.Column('observed_at', sa.DateTime(), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('created_by', sa.String(length=160), nullable=False),
    sa.Column('updated_at', sa.DateTime(), nullable=False),
    sa.Column('updated_by', sa.String(length=160), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('original_comment', sa.Text(), nullable=False),
    sa.Column('equipment_description', sa.Text(), nullable=False),
    sa.Column('facts', sa.Text(), nullable=False),
    sa.Column('recommendation', sa.Text(), nullable=False),
    sa.CheckConstraint('version >= 1', name='ck_maintenance_observation_version'),
    sa.ForeignKeyConstraint(['customer_branch_id'], ['customer_branches.id'], ),
    sa.ForeignKeyConstraint(['customer_id'], ['customer.id'], ),
    sa.ForeignKeyConstraint(['equipment_id'], ['customer_equipment.id'], ),
    sa.ForeignKeyConstraint(['source_order_id'], ['order.id'], ),
    sa.ForeignKeyConstraint(['storefront_id'], ['storefront.id'], ),
    sa.ForeignKeyConstraint(['tenant_id'], ['tenant.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source_order_id', 'command_key', name='uq_maintenance_observation_command')
    )
    with op.batch_alter_table('maintenance_observation', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_maintenance_observation_customer_branch_id'), ['customer_branch_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_maintenance_observation_customer_id'), ['customer_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_maintenance_observation_equipment_id'), ['equipment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_maintenance_observation_source_order_id'), ['source_order_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_maintenance_observation_storefront_id'), ['storefront_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_maintenance_observation_tenant_id'), ['tenant_id'], unique=False)

    op.create_table('maintenance_observation_photo',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('observation_id', sa.Integer(), nullable=False),
    sa.Column('attachment_id', sa.Integer(), nullable=False),
    sa.Column('command_key', sa.String(length=36), nullable=False),
    sa.Column('command_hash', sa.String(length=64), nullable=False),
    sa.ForeignKeyConstraint(['attachment_id'], ['service_attachment.id'], ),
    sa.ForeignKeyConstraint(['observation_id'], ['maintenance_observation.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('attachment_id', name='uq_maintenance_observation_photo_attachment'),
    sa.UniqueConstraint('observation_id', 'command_key', name='uq_maintenance_observation_photo_command')
    )
    with op.batch_alter_table('maintenance_observation_photo', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_maintenance_observation_photo_attachment_id'), ['attachment_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_maintenance_observation_photo_observation_id'), ['observation_id'], unique=False)

    op.create_table('maintenance_observation_revision',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('observation_id', sa.Integer(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('actor', sa.String(length=160), nullable=False),
    sa.Column('created_at', sa.DateTime(), nullable=False),
    sa.Column('snapshot', sa.JSON(), nullable=False),
    sa.ForeignKeyConstraint(['observation_id'], ['maintenance_observation.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('observation_id', 'version', name='uq_maintenance_observation_revision')
    )
    with op.batch_alter_table('maintenance_observation_revision', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_maintenance_observation_revision_observation_id'), ['observation_id'], unique=False)



def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table('maintenance_observation_revision', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_maintenance_observation_revision_observation_id'))

    op.drop_table('maintenance_observation_revision')
    with op.batch_alter_table('maintenance_observation_photo', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_maintenance_observation_photo_observation_id'))
        batch_op.drop_index(batch_op.f('ix_maintenance_observation_photo_attachment_id'))

    op.drop_table('maintenance_observation_photo')
    with op.batch_alter_table('maintenance_observation', schema=None) as batch_op:
        batch_op.drop_index(batch_op.f('ix_maintenance_observation_tenant_id'))
        batch_op.drop_index(batch_op.f('ix_maintenance_observation_storefront_id'))
        batch_op.drop_index(batch_op.f('ix_maintenance_observation_source_order_id'))
        batch_op.drop_index(batch_op.f('ix_maintenance_observation_equipment_id'))
        batch_op.drop_index(batch_op.f('ix_maintenance_observation_customer_id'))
        batch_op.drop_index(batch_op.f('ix_maintenance_observation_customer_branch_id'))

    op.drop_table('maintenance_observation')
