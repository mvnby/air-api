"""Persist the selected speech provider and deferred Google operation."""
from alembic import op
import sqlalchemy as sa

revision = "b1086ga11d02"
down_revision = "a1086ca11d01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("call_drive_connection", sa.Column("transcription_provider", sa.String(), nullable=False, server_default="groq"))
    op.add_column("call_recording", sa.Column("transcription_provider", sa.String(), nullable=True))
    op.add_column("call_recording", sa.Column("transcription_model", sa.String(), nullable=True))
    op.add_column("call_recording", sa.Column("transcription_operation", sa.String(), nullable=True))
    op.add_column("call_recording", sa.Column("transcription_submitted_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    for column in ("transcription_submitted_at", "transcription_operation", "transcription_model", "transcription_provider"):
        op.drop_column("call_recording", column)
    op.drop_column("call_drive_connection", "transcription_provider")
