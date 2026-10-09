"""Persist private Soniox input and its regional endpoint."""
from alembic import op
import sqlalchemy as sa

revision = "c1086so11d03"
down_revision = "b1086ga11d02"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("call_recording", sa.Column("soniox_file_id", sa.String(), nullable=True))
    op.add_column("call_recording", sa.Column("soniox_api_base_url", sa.String(), nullable=True))


def downgrade():
    op.drop_column("call_recording", "soniox_api_base_url")
    op.drop_column("call_recording", "soniox_file_id")
