"""Company tender module settings.

Revision ID: tnd20261126module01
Revises: doc20261120external01
"""

import sqlalchemy as sa
from alembic import op


revision = "tnd20261126module01"
down_revision = "doc20261120external01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tenant_tender_module",
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("entitled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("profiles", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("NOT enabled OR entitled", name="ck_tender_module_entitled"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenant.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("tenant_id"),
    )


def downgrade() -> None:
    op.drop_table("tenant_tender_module")
