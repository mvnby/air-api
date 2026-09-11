"""Add explicit equipment warranty mode and independent maintenance plan.

Revision ID: e57c3d4e5f6
Revises: e56b2c3d4e5
"""

from alembic import op
import sqlalchemy as sa


revision = "e57c3d4e5f6"
down_revision = "e56b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("customer_equipment") as batch_op:
        batch_op.add_column(
            sa.Column("warranty_mode", sa.String(length=16), nullable=False, server_default="auto")
        )
        batch_op.add_column(sa.Column("warranty_duration_months", sa.Integer(), nullable=True))
        batch_op.add_column(
            sa.Column("maintenance_enabled", sa.Boolean(), nullable=False, server_default=sa.false())
        )
        batch_op.add_column(
            sa.Column("maintenance_interval_months", sa.Integer(), nullable=False, server_default="12")
        )
        batch_op.add_column(sa.Column("maintenance_anchor_at", sa.DateTime(), nullable=True))
        batch_op.create_check_constraint(
            "ck_customer_equipment_warranty_mode",
            "warranty_mode IN ('auto', 'manual', 'none')",
        )
        batch_op.create_check_constraint(
            "ck_customer_equipment_warranty_duration_months",
            "warranty_duration_months IS NULL OR "
            "(warranty_duration_months >= 1 AND warranty_duration_months <= 240)",
        )
        batch_op.create_check_constraint(
            "ck_customer_equipment_maintenance_interval_months",
            "maintenance_interval_months >= 1 AND maintenance_interval_months <= 120",
        )
        batch_op.create_index(batch_op.f("ix_customer_equipment_warranty_mode"), ["warranty_mode"], unique=False)
        batch_op.create_index(
            batch_op.f("ix_customer_equipment_maintenance_enabled"),
            ["maintenance_enabled"],
            unique=False,
        )
        batch_op.create_index(
            batch_op.f("ix_customer_equipment_maintenance_anchor_at"),
            ["maintenance_anchor_at"],
            unique=False,
        )

def downgrade() -> None:
    with op.batch_alter_table("customer_equipment") as batch_op:
        batch_op.drop_index(batch_op.f("ix_customer_equipment_maintenance_anchor_at"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_maintenance_enabled"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_warranty_mode"))
        batch_op.drop_constraint("ck_customer_equipment_maintenance_interval_months", type_="check")
        batch_op.drop_constraint("ck_customer_equipment_warranty_duration_months", type_="check")
        batch_op.drop_constraint("ck_customer_equipment_warranty_mode", type_="check")
        batch_op.drop_column("maintenance_anchor_at")
        batch_op.drop_column("maintenance_interval_months")
        batch_op.drop_column("maintenance_enabled")
        batch_op.drop_column("warranty_duration_months")
        batch_op.drop_column("warranty_mode")
