"""Immutable maintenance offers, audited consent and factual resolution.

Revision ID: f13d5e6f7081
Revises: f12c4d5e6f70
"""
from alembic import op
import sqlalchemy as sa

revision = 'f13d5e6f7081'
down_revision = 'f12c4d5e6f70'
branch_labels = None
depends_on = None
TABLES = ('maintenance_offer', 'maintenance_offer_source', 'maintenance_offer_event', 'maintenance_resolution')


def upgrade():
    op.create_table('maintenance_offer',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('continuation_id', sa.Integer(), sa.ForeignKey('maintenance_continuation.id'), nullable=False),
        sa.Column('proposal_id', sa.Integer(), sa.ForeignKey('order_proposal.id'), nullable=False),
        sa.Column('command_key', sa.String(), nullable=False), sa.Column('command_hash', sa.String(), nullable=False),
        sa.Column('snapshot', sa.JSON(), nullable=False), sa.Column('created_by', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('continuation_id', 'command_key', name='uq_maintenance_offer_command'))
    op.create_index('ix_maintenance_offer_continuation_id', 'maintenance_offer', ['continuation_id'])
    op.create_table('maintenance_offer_source',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('offer_id', sa.Integer(), sa.ForeignKey('maintenance_offer.id'), nullable=False),
        sa.Column('revision_id', sa.Integer(), sa.ForeignKey('maintenance_observation_revision.id'), nullable=False),
        sa.UniqueConstraint('offer_id', 'revision_id', name='uq_maintenance_offer_source'))
    op.create_index('ix_maintenance_offer_source_offer_id', 'maintenance_offer_source', ['offer_id'])
    op.create_table('maintenance_offer_event',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('offer_id', sa.Integer(), sa.ForeignKey('maintenance_offer.id'), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False), sa.Column('action', sa.String(), nullable=False),
        sa.Column('command_key', sa.String(), nullable=False), sa.Column('command_hash', sa.String(), nullable=False),
        sa.Column('details', sa.JSON(), nullable=False), sa.Column('actor', sa.String(), nullable=False),
        sa.Column('occurred_at', sa.DateTime(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.UniqueConstraint('offer_id', 'command_key', name='uq_maintenance_offer_event_command'),
        sa.UniqueConstraint('offer_id', 'version', name='uq_maintenance_offer_event_version'))
    op.create_index('ix_maintenance_offer_event_offer_id', 'maintenance_offer_event', ['offer_id'])
    op.create_table('maintenance_resolution',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('observation_id', sa.Integer(), sa.ForeignKey('maintenance_observation.id'), nullable=False, unique=True),
        sa.Column('revision_id', sa.Integer(), sa.ForeignKey('maintenance_observation_revision.id'), nullable=False),
        sa.Column('offer_id', sa.Integer(), sa.ForeignKey('maintenance_offer.id'), nullable=False),
        sa.Column('history_id', sa.Integer(), sa.ForeignKey('equipment_service_history.id')),
        sa.Column('command_key', sa.String(), nullable=False), sa.Column('command_hash', sa.String(), nullable=False),
        sa.Column('evidence', sa.String(), nullable=False), sa.Column('actor', sa.String(), nullable=False),
        sa.Column('resolved_at', sa.DateTime(), nullable=False), sa.Column('created_at', sa.DateTime(), nullable=False))
    op.execute('''CREATE FUNCTION guard_maintenance_commercial_evidence() RETURNS trigger LANGUAGE plpgsql AS $$
    BEGIN RAISE EXCEPTION 'Maintenance commercial evidence is immutable' USING ERRCODE = '23514'; END $$''')
    for table in TABLES:
        op.execute(f'CREATE TRIGGER immutable_{table} BEFORE UPDATE OR DELETE ON {table} FOR EACH ROW EXECUTE FUNCTION guard_maintenance_commercial_evidence()')


def downgrade():
    connection = op.get_bind()
    if any(connection.execute(sa.text(f'SELECT EXISTS (SELECT 1 FROM {table})')).scalar() for table in TABLES):
        raise RuntimeError('Export maintenance offers/decisions/resolutions before schema downgrade')
    for table in reversed(TABLES):
        op.drop_table(table)
    op.execute('DROP FUNCTION guard_maintenance_commercial_evidence()')
