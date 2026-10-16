"""Separate company staff responsibility from legacy order/installers ownership."""

from alembic import op
import sqlalchemy as sa

revision = "t1166respons01"
down_revision = "t1164bot01"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("order", sa.Column("responsible_staff_user_id", sa.Integer(), nullable=True))
    op.add_column("order", sa.Column("responsible_version", sa.Integer(), nullable=False, server_default="0"))
    op.create_foreign_key("fk_order_responsible_staff", "order", "staff_users", ["responsible_staff_user_id"], ["id"], ondelete="RESTRICT")
    op.create_foreign_key("fk_order_responsible_membership", "order", "tenant_membership", ["tenant_id", "responsible_staff_user_id"], ["tenant_id", "staff_user_id"], ondelete="RESTRICT")
    op.create_check_constraint("ck_order_responsible_tenant", "order", "responsible_staff_user_id IS NULL OR tenant_id IS NOT NULL")
    op.create_check_constraint("ck_order_responsible_version", "order", "responsible_version >= 0")
    op.create_index("ix_order_tenant_responsible", "order", ["tenant_id", "responsible_staff_user_id"])


def downgrade():
    op.drop_index("ix_order_tenant_responsible", table_name="order")
    for name in ("ck_order_responsible_version", "ck_order_responsible_tenant"):
        op.drop_constraint(name, "order", type_="check")
    for name in ("fk_order_responsible_membership", "fk_order_responsible_staff"):
        op.drop_constraint(name, "order", type_="foreignkey")
    op.drop_column("order", "responsible_version")
    op.drop_column("order", "responsible_staff_user_id")
