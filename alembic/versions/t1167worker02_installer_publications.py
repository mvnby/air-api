"""Manager-only material publication and collection instructions; no payment writes."""

from alembic import op
import sqlalchemy as sa

revision = "t1167worker02"
down_revision = "t1167worker01"
branch_labels = None
depends_on = None


def upgrade():
    op.create_unique_constraint("uq_order_attachment_link_id_order", "order_attachment_link", ["id", "order_id"])
    op.create_table(
        "installer_material_publication",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Integer(), nullable=False),
        sa.Column("order_attachment_link_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("revoked_at", sa.DateTime()),
        sa.UniqueConstraint("assignment_id", "order_attachment_link_id", name="uq_installer_material_assignment_link"),
        sa.ForeignKeyConstraint(["assignment_id", "tenant_id", "storefront_id", "order_id"], ["order_work_assignment.id", "order_work_assignment.tenant_id", "order_work_assignment.storefront_id", "order_work_assignment.order_id"], name="fk_installer_material_assignment_scope", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["order_attachment_link_id", "order_id"], ["order_attachment_link.id", "order_attachment_link.order_id"], name="fk_installer_material_order_link", ondelete="RESTRICT"),
    )
    for column in ("tenant_id", "order_id", "assignment_id"):
        op.create_index(f"ix_installer_material_publication_{column}", "installer_material_publication", [column])
    op.create_table(
        "installer_collection_instruction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("tenant_id", sa.Integer(), nullable=False),
        sa.Column("storefront_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("assignment_id", sa.Integer()),
        sa.Column("amount", sa.Numeric(14, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("financial_fingerprint", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("order_id", name="uq_installer_collection_order"),
        sa.ForeignKeyConstraint(["order_id", "tenant_id", "storefront_id"], ["order.id", "order.tenant_id", "order.storefront_id"], name="fk_installer_collection_order_scope", ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["assignment_id", "tenant_id", "storefront_id", "order_id"], ["order_work_assignment.id", "order_work_assignment.tenant_id", "order_work_assignment.storefront_id", "order_work_assignment.order_id"], name="fk_installer_collection_assignment_scope", ondelete="CASCADE"),
        sa.CheckConstraint("version >= 0", name="ck_installer_collection_version"),
        sa.CheckConstraint("amount IS NULL OR amount >= 0", name="ck_installer_collection_amount"),
        sa.CheckConstraint("currency IS NULL OR currency IN ('BYN','USD','EUR')", name="ck_installer_collection_currency"),
        sa.CheckConstraint("(assignment_id IS NULL AND amount IS NULL AND currency IS NULL) OR (assignment_id IS NOT NULL AND amount IS NOT NULL AND currency IS NOT NULL)", name="ck_installer_collection_complete"),
    )
    op.create_index("ix_installer_collection_instruction_tenant_id", "installer_collection_instruction", ["tenant_id"])


def downgrade():
    op.drop_table("installer_collection_instruction")
    op.drop_table("installer_material_publication")
    op.drop_constraint("uq_order_attachment_link_id_order", "order_attachment_link", type_="unique")
