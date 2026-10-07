"""Add maintenance document continuations without changing historical orders.

Revision ID: f12c4d5e6f70
Revises: f11b3c4d5e6f
"""
from alembic import op
import sqlalchemy as sa

revision = 'f12c4d5e6f70'
down_revision = 'f11b3c4d5e6f'
branch_labels = None
depends_on = None

ORDER_CONTEXT_GUARD = '''
CREATE FUNCTION guard_maintenance_order_context() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF (NEW.tenant_id, NEW.storefront_id, NEW.customer_id, NEW.customer_branch_id)
     IS DISTINCT FROM (OLD.tenant_id, OLD.storefront_id, OLD.customer_id, OLD.customer_branch_id)
     AND EXISTS (SELECT 1 FROM maintenance_continuation WHERE source_order_id = OLD.id OR order_id = OLD.id)
  THEN RAISE EXCEPTION 'Maintenance continuation customer/object scope is immutable' USING ERRCODE = '23514'; END IF;
  RETURN NEW;
END $$
'''
BRANCH_CONTEXT_GUARD = '''
CREATE FUNCTION guard_maintenance_branch_context() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.customer_id IS DISTINCT FROM OLD.customer_id
     AND EXISTS (SELECT 1 FROM maintenance_continuation WHERE customer_branch_id = OLD.id)
  THEN RAISE EXCEPTION 'Maintenance continuation object owner is immutable' USING ERRCODE = '23514'; END IF;
  RETURN NEW;
END $$
'''
CUSTOMER_CONTEXT_GUARD = '''
CREATE FUNCTION guard_maintenance_customer_context() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
  IF NEW.tenant_id IS DISTINCT FROM OLD.tenant_id
     AND EXISTS (SELECT 1 FROM maintenance_continuation WHERE customer_id = OLD.id)
  THEN RAISE EXCEPTION 'Maintenance continuation customer tenant is immutable' USING ERRCODE = '23514'; END IF;
  RETURN NEW;
END $$
'''


def upgrade():
    op.create_table('maintenance_continuation',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('source_order_id', sa.Integer(), sa.ForeignKey('order.id'), nullable=False, unique=True),
        sa.Column('order_id', sa.Integer(), sa.ForeignKey('order.id'), nullable=False, unique=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('storefront_id', sa.Integer(), sa.ForeignKey('storefront.id'), nullable=False),
        sa.Column('customer_id', sa.Integer(), sa.ForeignKey('customer.id'), nullable=False),
        sa.Column('customer_branch_id', sa.Integer(), sa.ForeignKey('customer_branches.id')),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(160), nullable=False))
    for field in ('customer_id', 'customer_branch_id'):
        op.create_index(f'ix_maintenance_continuation_{field}', 'maintenance_continuation', [field])
    op.create_table('maintenance_act_preparation',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('continuation_id', sa.Integer(), sa.ForeignKey('maintenance_continuation.id'), nullable=False),
        sa.Column('document_id', sa.Integer(), sa.ForeignKey('order_document.id'), unique=True),
        sa.Column('command_key', sa.String(36), nullable=False),
        sa.Column('command_hash', sa.String(64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('created_by', sa.String(160), nullable=False),
        sa.UniqueConstraint('continuation_id', 'command_key', name='uq_maintenance_act_command'))
    op.create_index('ix_maintenance_act_preparation_continuation_id', 'maintenance_act_preparation', ['continuation_id'])
    op.create_table('maintenance_act_source',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('preparation_id', sa.Integer(), sa.ForeignKey('maintenance_act_preparation.id'), nullable=False),
        sa.Column('revision_id', sa.Integer(), sa.ForeignKey('maintenance_observation_revision.id'), nullable=False),
        sa.UniqueConstraint('preparation_id', 'revision_id', name='uq_maintenance_act_source'))
    for field in ('preparation_id', 'revision_id'):
        op.create_index(f'ix_maintenance_act_source_{field}', 'maintenance_act_source', [field])
    for statement in (ORDER_CONTEXT_GUARD, BRANCH_CONTEXT_GUARD, CUSTOMER_CONTEXT_GUARD):
        op.execute(statement)
    for table, kind in (('order', 'order'), ('customer_branches', 'branch'), ('customer', 'customer')):
        op.execute(f'CREATE TRIGGER maintenance_{kind}_context BEFORE UPDATE ON "{table}" FOR EACH ROW EXECUTE FUNCTION guard_maintenance_{kind}_context()')


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text('SELECT EXISTS (SELECT 1 FROM maintenance_continuation)')).scalar():
        raise RuntimeError('Export maintenance continuation/document source data before schema downgrade')
    for table, kind in (('order', 'order'), ('customer_branches', 'branch'), ('customer', 'customer')):
        op.execute(f'DROP TRIGGER maintenance_{kind}_context ON "{table}"')
        op.execute(f'DROP FUNCTION guard_maintenance_{kind}_context()')
    for table in ('maintenance_act_source', 'maintenance_act_preparation', 'maintenance_continuation'):
        op.drop_table(table)
