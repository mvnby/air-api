"""extend customer equipment warranty

Revision ID: e4f5a6b7c8d9
Revises: d9e0f1a2b3c4
Create Date: 2026-06-18 10:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, Sequence[str], None] = "d9e0f1a2b3c4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("customer_equipment", schema=None) as batch_op:
        batch_op.add_column(sa.Column("catalog_product_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("source_order_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("equipment_source", sa.String(), nullable=False, server_default="unknown"))
        batch_op.add_column(sa.Column("installed_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("commissioned_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("warranty_started_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("warranty_expires_at", sa.DateTime(), nullable=True))
        batch_op.add_column(sa.Column("warranty_terms", sa.Text(), nullable=True))
        batch_op.create_foreign_key(
            "fk_customer_equipment_catalog_product_id_product",
            "product",
            ["catalog_product_id"],
            ["id"],
        )
        batch_op.create_foreign_key(
            "fk_customer_equipment_source_order_id_order",
            "order",
            ["source_order_id"],
            ["id"],
        )
        batch_op.create_index(batch_op.f("ix_customer_equipment_catalog_product_id"), ["catalog_product_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_source_order_id"), ["source_order_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_equipment_source"), ["equipment_source"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_installed_at"), ["installed_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_commissioned_at"), ["commissioned_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_warranty_started_at"), ["warranty_started_at"], unique=False)
        batch_op.create_index(batch_op.f("ix_customer_equipment_warranty_expires_at"), ["warranty_expires_at"], unique=False)

    op.create_table(
        "equipment_component",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("equipment_id", sa.Integer(), nullable=False),
        sa.Column("catalog_product_id", sa.Integer(), nullable=True),
        sa.Column("supplier_id", sa.Integer(), nullable=True),
        sa.Column("component_type", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=True),
        sa.Column("brand", sa.String(), nullable=True),
        sa.Column("model", sa.String(), nullable=True),
        sa.Column("serial", sa.String(), nullable=True),
        sa.Column("inventory_number", sa.String(), nullable=True),
        sa.Column("supplier_invoice_number", sa.String(), nullable=True),
        sa.Column("supplier_invoice_date", sa.DateTime(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["catalog_product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["equipment_id"], ["customer_equipment.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_equipment_component_catalog_product_id"), "equipment_component", ["catalog_product_id"], unique=False)
    op.create_index(op.f("ix_equipment_component_component_type"), "equipment_component", ["component_type"], unique=False)
    op.create_index(op.f("ix_equipment_component_equipment_id"), "equipment_component", ["equipment_id"], unique=False)
    op.create_index(op.f("ix_equipment_component_inventory_number"), "equipment_component", ["inventory_number"], unique=False)
    op.create_index(op.f("ix_equipment_component_is_archived"), "equipment_component", ["is_archived"], unique=False)
    op.create_index(op.f("ix_equipment_component_model"), "equipment_component", ["model"], unique=False)
    op.create_index(op.f("ix_equipment_component_serial"), "equipment_component", ["serial"], unique=False)
    op.create_index(op.f("ix_equipment_component_supplier_id"), "equipment_component", ["supplier_id"], unique=False)
    op.create_index(op.f("ix_equipment_component_supplier_invoice_date"), "equipment_component", ["supplier_invoice_date"], unique=False)
    op.create_index(op.f("ix_equipment_component_supplier_invoice_number"), "equipment_component", ["supplier_invoice_number"], unique=False)
    op.create_index(op.f("ix_equipment_component_title"), "equipment_component", ["title"], unique=False)
    op.create_index(op.f("ix_equipment_component_brand"), "equipment_component", ["brand"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_equipment_component_brand"), table_name="equipment_component")
    op.drop_index(op.f("ix_equipment_component_title"), table_name="equipment_component")
    op.drop_index(op.f("ix_equipment_component_supplier_invoice_number"), table_name="equipment_component")
    op.drop_index(op.f("ix_equipment_component_supplier_invoice_date"), table_name="equipment_component")
    op.drop_index(op.f("ix_equipment_component_supplier_id"), table_name="equipment_component")
    op.drop_index(op.f("ix_equipment_component_serial"), table_name="equipment_component")
    op.drop_index(op.f("ix_equipment_component_model"), table_name="equipment_component")
    op.drop_index(op.f("ix_equipment_component_is_archived"), table_name="equipment_component")
    op.drop_index(op.f("ix_equipment_component_inventory_number"), table_name="equipment_component")
    op.drop_index(op.f("ix_equipment_component_equipment_id"), table_name="equipment_component")
    op.drop_index(op.f("ix_equipment_component_component_type"), table_name="equipment_component")
    op.drop_index(op.f("ix_equipment_component_catalog_product_id"), table_name="equipment_component")
    op.drop_table("equipment_component")

    with op.batch_alter_table("customer_equipment", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_customer_equipment_warranty_expires_at"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_warranty_started_at"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_commissioned_at"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_installed_at"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_equipment_source"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_source_order_id"))
        batch_op.drop_index(batch_op.f("ix_customer_equipment_catalog_product_id"))
        batch_op.drop_constraint("fk_customer_equipment_source_order_id_order", type_="foreignkey")
        batch_op.drop_constraint("fk_customer_equipment_catalog_product_id_product", type_="foreignkey")
        batch_op.drop_column("warranty_terms")
        batch_op.drop_column("warranty_expires_at")
        batch_op.drop_column("warranty_started_at")
        batch_op.drop_column("commissioned_at")
        batch_op.drop_column("installed_at")
        batch_op.drop_column("equipment_source")
        batch_op.drop_column("source_order_id")
        batch_op.drop_column("catalog_product_id")
