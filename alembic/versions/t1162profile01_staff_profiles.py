"""Private staff profiles and historical identity aliases.

Revision ID: t1162profile01
Revises: t1161access01
"""
from alembic import op
import sqlalchemy as sa

revision = "t1162profile01"
down_revision = "t1161access01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("staff_users", sa.Column("telegram_verified_at", sa.DateTime(timezone=True)))
    op.add_column("staff_users", sa.Column(
        "telegram_notifications_enabled", sa.Boolean(), nullable=False,
        server_default=sa.true(),
    ))
    op.add_column("staff_users", sa.Column("avatar_version", sa.String(64)))
    op.add_column("staff_users", sa.Column("merged_into_staff_user_id", sa.Integer()))
    op.create_foreign_key(
        "fk_staff_users_merged_into", "staff_users", "staff_users",
        ["merged_into_staff_user_id"], ["id"],
    )
    op.create_index("ix_staff_users_merged_into_staff_user_id", "staff_users", ["merged_into_staff_user_id"])
    op.create_table(
        "staff_avatar",
        sa.Column("staff_user_id", sa.Integer(), sa.ForeignKey("staff_users.id"), primary_key=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("staff_avatar")
    op.drop_index("ix_staff_users_merged_into_staff_user_id", table_name="staff_users")
    op.drop_constraint("fk_staff_users_merged_into", "staff_users", type_="foreignkey")
    op.drop_column("staff_users", "merged_into_staff_user_id")
    op.drop_column("staff_users", "avatar_version")
    op.drop_column("staff_users", "telegram_notifications_enabled")
    op.drop_column("staff_users", "telegram_verified_at")
