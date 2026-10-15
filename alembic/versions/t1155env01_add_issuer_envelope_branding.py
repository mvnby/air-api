"""Persist envelope-only branding on each tenant-owned issuer.

Revision ID: t1155env01
Revises: t1152conn01
"""

from alembic import op
import sqlalchemy as sa

revision = "t1155env01"
down_revision = "t1152conn01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("document_legal_entity", sa.Column(
        "envelope_branding", sa.JSON(), nullable=False, server_default=sa.text("'{}'"),
    ))


def downgrade():
    op.drop_column("document_legal_entity", "envelope_branding")
