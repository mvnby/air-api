"""Store versioned inspections for the equipment of one order site.

Revision ID: order1278diag01
Revises: order1278sites01
"""

import sqlalchemy as sa
from alembic import op


revision = "order1278diag01"
down_revision = "order1278sites01"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "order_inspection_revision",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("order_id", sa.Integer(), nullable=False),
        sa.Column("site_id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("actor_staff_user_id", sa.Integer(), sa.ForeignKey("staff_users.id"), nullable=False),
        sa.Column("recorded_by", sa.String(length=160), nullable=False),
        sa.Column("facts", sa.JSON(), nullable=False),
        sa.ForeignKeyConstraint(
            ["order_id", "site_id", "equipment_id"],
            ["order_site_equipment.order_id", "order_site_equipment.site_id", "order_site_equipment.equipment_id"],
            name="fk_order_inspection_revision_site_equipment",
            ondelete="CASCADE",
        ),
        sa.UniqueConstraint(
            "order_id", "site_id", "equipment_id", "version",
            name="uq_order_inspection_revision_version",
        ),
        sa.CheckConstraint("version >= 1", name="ck_order_inspection_revision_version"),
    )


def downgrade() -> None:
    op.drop_table("order_inspection_revision")
