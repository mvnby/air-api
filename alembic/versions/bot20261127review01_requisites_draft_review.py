"""Bind Telegram requisites actions to the reviewed draft and duplicate."""

from alembic import op
import sqlalchemy as sa

revision = "bot20261127review01"
down_revision = "inst20261126material01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customer_requisites_recognition", sa.Column(
        "review_edit_count", sa.Integer(), nullable=False, server_default="0",
    ))
    op.add_column("customer_requisites_recognition", sa.Column(
        "review_revision", sa.String(16), nullable=True,
    ))


def downgrade():
    op.drop_column("customer_requisites_recognition", "review_revision")
    op.drop_column("customer_requisites_recognition", "review_edit_count")
