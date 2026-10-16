"""Explicit worker profiles/work assignments. DDL only; no historical access grants."""
from alembic import op
import sqlalchemy as sa

revision = "t1167worker01"
down_revision = "t1166respons01"
branch_labels = None
depends_on = None


def upgrade():
    op.drop_constraint("ck_staff_invitation_role", "staff_invitation", type_="check")
    op.create_check_constraint("ck_staff_invitation_role", "staff_invitation", "role IN ('owner','admin','manager','catalog_editor','installer')")
    op.create_unique_constraint("uq_work_stage_id_order", "order_work_stage", ["id", "order_id"])
    op.create_table("tenant_worker_profile",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), sa.ForeignKey("tenant.id"), nullable=False),
        sa.Column("staff_user_id", sa.Integer(), sa.ForeignKey("staff_users.id"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="active"),
        sa.Column("canonical_legacy_installer_id", sa.Integer(), sa.ForeignKey("installers.id")),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.UniqueConstraint("tenant_id", "staff_user_id", name="uq_worker_profile_tenant_staff"),
        sa.UniqueConstraint("id", "tenant_id", name="uq_worker_profile_id_tenant"),
        sa.ForeignKeyConstraint(["tenant_id", "staff_user_id"], ["tenant_membership.tenant_id", "tenant_membership.staff_user_id"], name="fk_worker_profile_membership", ondelete="RESTRICT"),
        sa.CheckConstraint("status IN ('active', 'disabled')", name="ck_worker_profile_status"),
        sa.CheckConstraint("version >= 0", name="ck_worker_profile_version"),
    )
    op.create_index("ix_tenant_worker_profile_tenant_id", "tenant_worker_profile", ["tenant_id"])
    op.create_index("ix_tenant_worker_profile_staff_user_id", "tenant_worker_profile", ["staff_user_id"])
    op.create_table("order_work_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("work_stage_id", sa.Integer()),
        sa.Column("worker_profile_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False, server_default=""),
        sa.Column("title", sa.String(160), nullable=False, server_default="Монтаж"),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.UniqueConstraint("id", "tenant_id", "storefront_id", "order_id", name="uq_work_assignment_id_scope"),
        sa.ForeignKeyConstraint(["order_id", "tenant_id", "storefront_id"], ["order.id", "order.tenant_id", "order.storefront_id"], name="fk_work_assignment_order_scope", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["work_stage_id", "order_id"], ["order_work_stage.id", "order_work_stage.order_id"], name="fk_work_assignment_stage_order", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["worker_profile_id", "tenant_id"], ["tenant_worker_profile.id", "tenant_worker_profile.tenant_id"], name="fk_work_assignment_profile_tenant", ondelete="RESTRICT"),
        sa.CheckConstraint("version >= 0", name="ck_work_assignment_version"),
        sa.CheckConstraint("source IN ('manual', 'legacy_order', 'legacy_stage')", name="ck_work_assignment_source"),
    )
    for column in ("tenant_id", "storefront_id", "order_id", "work_stage_id", "worker_profile_id"):
        op.create_index(f"ix_order_work_assignment_{column}", "order_work_assignment", [column])
    op.create_index("uq_work_assignment_active_order", "order_work_assignment", ["tenant_id", "order_id", "worker_profile_id"], unique=True,
                    postgresql_where=sa.text("revoked_at IS NULL AND work_stage_id IS NULL"))
    op.create_index("uq_work_assignment_active_stage", "order_work_assignment", ["tenant_id", "order_id", "work_stage_id", "worker_profile_id"], unique=True,
                    postgresql_where=sa.text("revoked_at IS NULL AND work_stage_id IS NOT NULL"))


def downgrade():
    if op.get_bind().execute(sa.text("SELECT 1 FROM staff_invitation WHERE role = 'installer' LIMIT 1")).first():
        raise RuntimeError("Cannot downgrade while installer invitations exist")
    op.drop_constraint("ck_staff_invitation_role", "staff_invitation", type_="check")
    op.create_check_constraint("ck_staff_invitation_role", "staff_invitation", "role IN ('owner','admin','manager','catalog_editor')")
    op.drop_table("order_work_assignment")
    op.drop_table("tenant_worker_profile")
    op.drop_constraint("uq_work_stage_id_order", "order_work_stage", type_="unique")
