"""Persist staff bot company/site selection and its monotonic revision."""

from alembic import op
import sqlalchemy as sa

revision = "t1164bot01"
down_revision = "t1164team01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bot_staff_selection",
        sa.Column(
            "staff_user_id",
            sa.Integer(),
            sa.ForeignKey("staff_users.id"),
            primary_key=True,
        ),
        sa.Column(
            "tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False
        ),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("context_version", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(
            ["storefront_id", "tenant_id"], ["storefront.id", "storefront.tenant_id"]
        ),
        sa.CheckConstraint(
            "context_version >= 0", name="ck_bot_staff_selection_version"
        ),
    )


def downgrade():
    op.drop_table("bot_staff_selection")
