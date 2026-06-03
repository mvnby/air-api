"""Add customer equipment service history

Revision ID: 2d6c4b8e9f31
Revises: 7c8d9e0f1a23
Create Date: 2026-06-03 21:40:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "2d6c4b8e9f31"
down_revision: Union[str, Sequence[str], None] = "7c8d9e0f1a23"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "customer_equipment",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("customer_id", sa.Integer(), nullable=False),
        sa.Column("customer_branch_id", sa.Integer(), nullable=True),
        sa.Column("equipment_type", sa.String(), nullable=False),
        sa.Column("display_name", sa.String(), nullable=True),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("serial", sa.String(), nullable=True),
        sa.Column("inventory_number", sa.String(), nullable=True),
        sa.Column("location_hint", sa.String(), nullable=True),
        sa.Column("refrigerant_type", sa.String(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["customer_branch_id"], ["customer_branches.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customer.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("customer_equipment", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_customer_equipment_brand"), ["brand"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_customer_branch_id"), ["customer_branch_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_customer_id"), ["customer_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_display_name"), ["display_name"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_equipment_type"), ["equipment_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_inventory_number"), ["inventory_number"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_is_archived"), ["is_archived"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_model"), ["model"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_refrigerant_type"), ["refrigerant_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_serial"), ["serial"], unique=False)

    op.create_table(
        "equipment_service_history",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("order_id", sa.Integer(), nullable=True),
        sa.Column("event_type", sa.String(), nullable=False),
        sa.Column("event_date", sa.DateTime(), nullable=False),
        sa.Column("complaint_snapshot", sa.Text(), nullable=True),
        sa.Column("diagnostic_result", sa.Text(), nullable=True),
        sa.Column("repair_recommendation", sa.Text(), nullable=True),
        sa.Column("refrigerant_type", sa.String(), nullable=True),
        sa.Column("refrigerant_amount", sa.String(), nullable=True),
        sa.Column("not_repairable", sa.Boolean(), nullable=False),
        sa.Column("not_repairable_reason", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["equipment_id"], ["customer_equipment.id"]),
        sa.ForeignKeyConstraint(["order_id"], ["order.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("equipment_service_history", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_equipment_service_history_equipment_id"), ["equipment_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_equipment_service_history_event_date"), ["event_date"], unique=False)
        batch_op.create_index(batch_op.f("ix_equipment_service_history_event_type"), ["event_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_equipment_service_history_not_repairable"), ["not_repairable"], unique=False)
        batch_op.create_index(batch_op.f("ix_equipment_service_history_order_id"), ["order_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_equipment_service_history_refrigerant_type"), ["refrigerant_type"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("equipment_service_history", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_equipment_service_history_refrigerant_type"))
        batch_op.drop_index(batch_op.f("ix_equipment_service_history_order_id"))
        batch_op.drop_index(batch_op.f("ix_equipment_service_history_not_repairable"))
        batch_op.drop_index(batch_op.f("ix_equipment_service_history_event_type"))
        batch_op.drop_index(batch_op.f("ix_equipment_service_history_event_date"))
        batch_op.drop_index(batch_op.f("ix_equipment_service_history_equipment_id"))
    op.drop_table("equipment_service_history")

    with op.batch_alter_table("customer_equipment", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_customer_equipment_serial"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_refrigerant_type"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_model"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_is_archived"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_inventory_number"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_equipment_type"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_display_name"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_customer_id"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_customer_branch_id"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_brand"))
    op.drop_table("customer_equipment")
