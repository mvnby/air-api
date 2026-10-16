"""One-use company invitations without automatic account attachment.

Revision ID: t1164team01
Revises: t1162telegram01
"""
from alembic import op
import sqlalchemy as sa

revision = "t1164team01"
down_revision = "t1162telegram01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table("staff_invitation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("created_by_staff_user_id", sa.Integer(), sa.ForeignKey("staff_users.id"), nullable=False),
        sa.Column("accepted_by_staff_user_id", sa.Integer(), sa.ForeignKey("staff_users.id")),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("role", sa.String(24), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.CheckConstraint("role IN ('owner','admin','manager','catalog_editor')", name="ck_staff_invitation_role"),
    )
    op.create_index("ix_staff_invitation_tenant_id", "staff_invitation", ["tenant_id"])


def downgrade():
    op.drop_index("ix_staff_invitation_tenant_id", table_name="staff_invitation")
    op.drop_table("staff_invitation")
