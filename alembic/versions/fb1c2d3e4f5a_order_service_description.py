"""Persist editable commercial service descriptions.

Revision ID: fb1c2d3e4f5a
Revises: fa0b1c2d3e4f
"""

from alembic import op
import sqlalchemy as sa

revision = "fb1c2d3e4f5a"
down_revision = "fa0b1c2d3e4f"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("order_service_link", sa.Column("description", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("order_service_link", "description")
