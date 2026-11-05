"""Persist units for commercial service lines."""

from alembic import op
import sqlalchemy as sa

revision = "mcp20261105unit01"
down_revision = "doc20261105reg01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("order_service_link", sa.Column("unit", sa.String(100), nullable=True))


def downgrade():
    op.drop_column("order_service_link", "unit")
