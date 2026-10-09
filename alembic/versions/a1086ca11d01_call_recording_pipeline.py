"""Durable private call recording pipeline, off by default."""
from alembic import op
import sqlalchemy as sa

revision = "a1086ca11d01"
down_revision = "f13d5e6f7081"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('call_drive_connection',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('tenant_id', sa.Integer(), sa.ForeignKey('tenant.id'), nullable=False),
        sa.Column('storefront_id', sa.Integer(), sa.ForeignKey('storefront.id'), nullable=False),
        sa.Column('staff_user_id', sa.Integer(), sa.ForeignKey('staff_users.id'), nullable=False),
        sa.Column('encrypted_credentials', sa.Text(), nullable=True),
        sa.Column('credentials_fingerprint', sa.String(), nullable=False),
        sa.Column('account_label', sa.String(), nullable=True),
        sa.Column('folder_id', sa.String(), nullable=True),
        sa.Column('folder_name', sa.String(), nullable=True),
        sa.Column('auto_poll_enabled', sa.Boolean(), nullable=False),
        sa.Column('page_token', sa.String(), nullable=True),
        sa.Column('last_error_code', sa.String(), nullable=True),
        sa.Column('last_polled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('tenant_id', 'storefront_id', 'staff_user_id', name='uq_call_drive_owner'),
    )
    op.create_table('call_recording',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('connection_id', sa.Integer(), sa.ForeignKey('call_drive_connection.id'), nullable=False),
        sa.Column('file_id', sa.String(), nullable=False),
        sa.Column('source_version', sa.String(), nullable=False),
        sa.Column('source_checksum', sa.String(), nullable=False),
        sa.Column('source_size', sa.Integer(), nullable=False),
        sa.Column('source_url', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('mime_type', sa.String(), nullable=False),
        sa.Column('source_modified_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('call_occurred_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('time_source', sa.String(), nullable=False),
        sa.Column('phone', sa.String(), nullable=True),
        sa.Column('origin', sa.String(), nullable=False),
        sa.Column('state', sa.String(), nullable=False),
        sa.Column('stage', sa.String(), nullable=False),
        sa.Column('observations', sa.Integer(), nullable=False),
        sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('downloaded_audio', sa.LargeBinary(), nullable=True),
        sa.Column('audio_duration_seconds', sa.Float(), nullable=True),
        sa.Column('transcript', sa.Text(), nullable=True),
        sa.Column('structure', sa.JSON(), nullable=True),
        sa.Column('stage_attempts', sa.JSON(), nullable=False),
        sa.Column('last_error_code', sa.String(), nullable=True),
        sa.Column('job_event_id', sa.String(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('connection_id', 'file_id', 'source_version', name='uq_call_recording_version'),
    )
    op.create_index('ix_call_recording_state', 'call_recording', ['state'])
    op.create_index('ix_call_recording_connection_id', 'call_recording', ['connection_id'])
    op.create_table('call_proposal',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('recording_id', sa.Integer(), sa.ForeignKey('call_recording.id'), nullable=False),
        sa.Column('action_key', sa.String(), nullable=False),
        sa.Column('kind', sa.String(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('evidence', sa.Text(), nullable=False),
        sa.Column('needs_clarification', sa.JSON(), nullable=False),
        sa.UniqueConstraint('recording_id', 'action_key', name='uq_call_proposal_action'),
    )
    op.create_index('ix_call_proposal_recording_id', 'call_proposal', ['recording_id'])
    op.create_table('call_adoption',
        sa.Column('id', sa.Integer(), nullable=False, primary_key=True),
        sa.Column('connection_id', sa.Integer(), sa.ForeignKey('call_drive_connection.id'), nullable=False),
        sa.Column('file_id', sa.String(), nullable=False),
        sa.Column('action_key', sa.String(), nullable=False),
        sa.Column('proposal_id', sa.Integer(), sa.ForeignKey('call_proposal.id'), nullable=False),
        sa.Column('resource_type', sa.String(), nullable=False),
        sa.Column('resource_id', sa.Integer(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint('connection_id', 'file_id', 'action_key', name='uq_call_adoption_source_action'),
    )


def downgrade():
    connection = op.get_bind()
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM call_adoption)")).scalar():
        raise RuntimeError("Export call material before schema downgrade")
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM call_proposal)")).scalar():
        raise RuntimeError("Export call material before schema downgrade")
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM call_recording)")).scalar():
        raise RuntimeError("Export call material before schema downgrade")
    if connection.execute(sa.text("SELECT EXISTS (SELECT 1 FROM call_drive_connection)")).scalar():
        raise RuntimeError("Export call material before schema downgrade")
    op.drop_table('call_adoption')
    op.drop_table('call_proposal')
    op.drop_table('call_recording')
    op.drop_table('call_drive_connection')
