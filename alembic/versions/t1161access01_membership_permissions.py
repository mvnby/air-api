"""Explicit, tenant-bound delegated catalog permissions.

Revision ID: t1161access01
Revises: t1155env01
"""

from alembic import op
import sqlalchemy as sa

revision = "t1161access01"
down_revision = "t1155env01"
branch_labels = None
depends_on = None


def upgrade():
    # No implicit grants: company membership must not create platform authority.
    op.add_column("tenant_membership", sa.Column(
        "permissions", sa.JSON(), nullable=False, server_default=sa.text("'[]'"),
    ))


def downgrade():
    op.drop_column("tenant_membership", "permissions")
