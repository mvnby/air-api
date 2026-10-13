"""Record authenticated MCP use without changing existing grants.

Revision ID: t1152conn01
Revises: t1090mail01
"""

from alembic import op
import sqlalchemy as sa

revision = "t1152conn01"
down_revision = "t1090mail01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("connector_grant", sa.Column(
        "last_used_at", sa.DateTime(timezone=True), nullable=True
    ))


def downgrade():
    op.drop_column("connector_grant", "last_used_at")
