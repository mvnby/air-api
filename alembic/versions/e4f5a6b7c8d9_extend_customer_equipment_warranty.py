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


def _table_exists(table_name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(table_name)


def _column_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {column["name"] for column in sa.inspect(op.get_bind()).get_columns(table_name)}


def _index_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {index["name"] for index in sa.inspect(op.get_bind()).get_indexes(table_name)}


def _foreign_key_names(table_name: str) -> set[str]:
    if not _table_exists(table_name):
        return set()
    return {fk["name"] for fk in sa.inspect(op.get_bind()).get_foreign_keys(table_name) if fk.get("name")}


def _create_index_if_missing(index_name: str, table_name: str, columns: list[str]) -> None:
    if index_name not in _index_names(table_name):
        op.create_index(index_name, table_name, columns, unique=False)


def upgrade() -> None:
    """Upgrade schema."""
    equipment_columns = _column_names("customer_equipment")
    equipment_indexes = _index_names("customer_equipment")
    equipment_fks = _foreign_key_names("customer_equipment")
    with op.batch_alter_table("customer_equipment", schema=None) as batch_op:
        if "catalog_product_id" not in equipment_columns:
            batch_op.add_column(sa.Column("catalog_product_id", sa.Integer(), nullable=True))
        if "source_order_id" not in equipment_columns:
            batch_op.add_column(sa.Column("source_order_id", sa.Integer(), nullable=True))
        if "equipment_source" not in equipment_columns:
            batch_op.add_column(sa.Column("equipment_source", sa.String(), nullable=False, server_default="unknown"))
        if "installed_at" not in equipment_columns:
            batch_op.add_column(sa.Column("installed_at", sa.DateTime(), nullable=True))
        if "commissioned_at" not in equipment_columns:
            batch_op.add_column(sa.Column("commissioned_at", sa.DateTime(), nullable=True))
        if "warranty_started_at" not in equipment_columns:
            batch_op.add_column(sa.Column("warranty_started_at", sa.DateTime(), nullable=True))
        if "warranty_expires_at" not in equipment_columns:
            batch_op.add_column(sa.Column("warranty_expires_at", sa.DateTime(), nullable=True))
        if "warranty_terms" not in equipment_columns:
            batch_op.add_column(sa.Column("warranty_terms", sa.Text(), nullable=True))
        if "fk_customer_equipment_catalog_product_id_product" not in equipment_fks:
            batch_op.create_foreign_key(
                "fk_customer_equipment_catalog_product_id_product",
                "product",
                ["catalog_product_id"],
                ["id"],
            )
        if "fk_customer_equipment_source_order_id_order" not in equipment_fks:
            batch_op.create_foreign_key(
                "fk_customer_equipment_source_order_id_order",
                "order",
                ["source_order_id"],
                ["id"],
            )
        if "ix_customer_equipment_catalog_product_id" not in equipment_indexes:
            batch_op.create_index(batch_op.f("ix_customer_equipment_catalog_product_id"), ["catalog_product_id"], unique=False)
        if "ix_customer_equipment_source_order_id" not in equipment_indexes:
            batch_op.create_index(batch_op.f("ix_customer_equipment_source_order_id"), ["source_order_id"], unique=False)
        if "ix_customer_equipment_equipment_source" not in equipment_indexes:
            batch_op.create_index(batch_op.f("ix_customer_equipment_equipment_source"), ["equipment_source"], unique=False)
        if "ix_customer_equipment_installed_at" not in equipment_indexes:
            batch_op.create_index(batch_op.f("ix_customer_equipment_installed_at"), ["installed_at"], unique=False)
        if "ix_customer_equipment_commissioned_at" not in equipment_indexes:
            batch_op.create_index(batch_op.f("ix_customer_equipment_commissioned_at"), ["commissioned_at"], unique=False)
        if "ix_customer_equipment_warranty_started_at" not in equipment_indexes:
            batch_op.create_index(batch_op.f("ix_customer_equipment_warranty_started_at"), ["warranty_started_at"], unique=False)
        if "ix_customer_equipment_warranty_expires_at" not in equipment_indexes:
            batch_op.create_index(batch_op.f("ix_customer_equipment_warranty_expires_at"), ["warranty_expires_at"], unique=False)

    if not _table_exists("equipment_component"):
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
    _create_index_if_missing(op.f("ix_equipment_component_catalog_product_id"), "equipment_component", ["catalog_product_id"])
    _create_index_if_missing(op.f("ix_equipment_component_component_type"), "equipment_component", ["component_type"])
    _create_index_if_missing(op.f("ix_equipment_component_equipment_id"), "equipment_component", ["equipment_id"])
    _create_index_if_missing(op.f("ix_equipment_component_inventory_number"), "equipment_component", ["inventory_number"])
    _create_index_if_missing(op.f("ix_equipment_component_is_archived"), "equipment_component", ["is_archived"])
    _create_index_if_missing(op.f("ix_equipment_component_model"), "equipment_component", ["model"])
    _create_index_if_missing(op.f("ix_equipment_component_serial"), "equipment_component", ["serial"])
    _create_index_if_missing(op.f("ix_equipment_component_supplier_id"), "equipment_component", ["supplier_id"])
    _create_index_if_missing(op.f("ix_equipment_component_supplier_invoice_date"), "equipment_component", ["supplier_invoice_date"])
    _create_index_if_missing(op.f("ix_equipment_component_supplier_invoice_number"), "equipment_component", ["supplier_invoice_number"])
    _create_index_if_missing(op.f("ix_equipment_component_title"), "equipment_component", ["title"])
    _create_index_if_missing(op.f("ix_equipment_component_brand"), "equipment_component", ["brand"])


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
