"""Add internal titles and deletion timestamps to personal offers."""

import sqlalchemy as sa
from alembic import op

revision = "t1295offer02"
down_revision = "t1286offer01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("personal_offer", sa.Column("title", sa.String(100)))
    op.add_column("personal_offer", sa.Column("deleted_at", sa.DateTime(timezone=True)))


def downgrade():
    op.drop_column("personal_offer", "deleted_at")
    op.drop_column("personal_offer", "title")
