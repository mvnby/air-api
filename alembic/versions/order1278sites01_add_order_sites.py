"""Add order sites and site equipment without rewriting legacy orders."""

from alembic import op
import sqlalchemy as sa


revision = "order1278sites01"
down_revision = "doc20261110audit01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_site",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("customer_branch_id", sa.Integer(), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.ForeignKeyConstraint(["customer_branch_id"], ["customer_branches.id"], ondelete="SET NULL"),
        sa.UniqueConstraint("order_id", "id", name="uq_order_site_order_id"),
        sa.UniqueConstraint("order_id", "customer_branch_id", name="uq_order_site_order_branch"),
        sa.CheckConstraint("version >= 1", name="ck_order_site_version"),
    )
    op.create_index("ix_order_site_order_id", "order_site", ["order_id"])
    op.create_index("ix_order_site_customer_branch_id", "order_site", ["customer_branch_id"])
    op.create_table(
        "order_site_equipment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id", "site_id"], ["order_site.order_id", "order_site.id"],
            name="fk_order_site_equipment_site", ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["equipment_id"], ["customer_equipment.id"]),
        sa.UniqueConstraint("order_id", "equipment_id", name="uq_order_site_equipment_order_unit"),
        sa.UniqueConstraint(
            "order_id", "site_id", "equipment_id", name="uq_order_site_equipment_order_site_unit",
        ),
    )
    op.create_index("ix_order_site_equipment_site_id", "order_site_equipment", ["site_id"])
    op.create_index("ix_order_site_equipment_equipment_id", "order_site_equipment", ["equipment_id"])


def downgrade() -> None:
    op.drop_table("order_site_equipment")
    op.drop_table("order_site")
