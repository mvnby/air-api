"""add supply requests and supplier profile

Revision ID: f7a8b9c0d1e2
Revises: e5f6a7b8c9d1
Create Date: 2026-07-08 15:30:00.000000

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "f7a8b9c0d1e2"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("supplier", sa.Column("legal_name", sa.String(), nullable=True))
    op.add_column("supplier", sa.Column("tax_id", sa.String(), nullable=True))
    op.add_column("supplier", sa.Column("legal_address", sa.String(), nullable=True))
    op.add_column("supplier", sa.Column("postal_address", sa.String(), nullable=True))
    op.add_column(
        "supplier",
        sa.Column("default_payment_method", sa.String(), nullable=False, server_default="unknown"),
    )
    op.add_column("supplier", sa.Column("payment_comment", sa.Text(), nullable=True))
    op.create_index("ix_supplier_tax_id", "supplier", ["tax_id"], unique=False)

    op.create_table(
        "supplier_contact",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=True),
        sa.Column("phone", sa.String(), nullable=True),
        sa.Column("viber", sa.String(), nullable=True),
        sa.Column("telegram_username", sa.String(), nullable=True),
        sa.Column("telegram_chat_id", sa.String(), nullable=True),
        sa.Column("email", sa.String(), nullable=True),
        sa.Column("preferred_channel", sa.String(), nullable=False, server_default="phone"),
        sa.Column("default_for_orders", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_for_logistics", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_supplier_contact_supplier_id", "supplier_contact", ["supplier_id"], unique=False)
    op.create_index("ix_supplier_contact_default_for_orders", "supplier_contact", ["default_for_orders"], unique=False)
    op.create_index("ix_supplier_contact_default_for_logistics", "supplier_contact", ["default_for_logistics"], unique=False)

    op.create_table(
        "supplier_warehouse",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("address", sa.Text(), nullable=False),
        sa.Column("contact_id", sa.Integer(), nullable=True),
        sa.Column("contact_name", sa.String(), nullable=True),
        sa.Column("contact_phone", sa.String(), nullable=True),
        sa.Column("work_hours", sa.String(), nullable=True),
        sa.Column("pickup_notes", sa.Text(), nullable=True),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["contact_id"], ["supplier_contact.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_supplier_warehouse_supplier_id", "supplier_warehouse", ["supplier_id"], unique=False)
    op.create_index("ix_supplier_warehouse_contact_id", "supplier_warehouse", ["contact_id"], unique=False)
    op.create_index("ix_supplier_warehouse_is_default", "supplier_warehouse", ["is_default"], unique=False)

    op.create_table(
        "supply_request",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_id", sa.Integer(), nullable=True),
        sa.Column("supplier_contact_id", sa.Integer(), nullable=True),
        sa.Column("logistics_contact_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("intent", sa.String(), nullable=False, server_default="order"),
        sa.Column("payment_method", sa.String(), nullable=False, server_default="unknown"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("supplier_message_snapshot", sa.Text(), nullable=True),
        sa.Column("logistics_message_snapshot", sa.Text(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("supplier_message_sent_at", sa.DateTime(), nullable=True),
        sa.Column("logistics_message_sent_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["logistics_contact_id"], ["supplier_contact.id"]),
        sa.ForeignKeyConstraint(["supplier_contact_id"], ["supplier_contact.id"]),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"]),
        sa.ForeignKeyConstraint(["warehouse_id"], ["supplier_warehouse.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_supply_request_supplier_id", "supply_request", ["supplier_id"], unique=False)
    op.create_index("ix_supply_request_warehouse_id", "supply_request", ["warehouse_id"], unique=False)
    op.create_index("ix_supply_request_supplier_contact_id", "supply_request", ["supplier_contact_id"], unique=False)
    op.create_index("ix_supply_request_logistics_contact_id", "supply_request", ["logistics_contact_id"], unique=False)
    op.create_index("ix_supply_request_status", "supply_request", ["status"], unique=False)
    op.create_index("ix_supply_request_intent", "supply_request", ["intent"], unique=False)
    op.create_index("ix_supply_request_payment_method", "supply_request", ["payment_method"], unique=False)
    op.create_index("ix_supply_request_created_by", "supply_request", ["created_by"], unique=False)
    op.create_index("ix_supply_request_created_at", "supply_request", ["created_at"], unique=False)

    op.create_table(
        "supply_request_line",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("request_id", sa.Integer(), nullable=False),
        sa.Column("order_product_link_id", sa.Integer(), nullable=True),
        sa.Column("source_type", sa.String(), nullable=False, server_default="manual"),
        sa.Column("product_id", sa.Integer(), nullable=True),
        sa.Column("supplier_offer_external_id", sa.String(), nullable=True),
        sa.Column("supplier_offer_title", sa.String(), nullable=True),
        sa.Column("title_snapshot", sa.String(), nullable=False),
        sa.Column("qty", sa.Integer(), nullable=False),
        sa.Column("unit_cost_snapshot", sa.Numeric(12, 2), nullable=True),
        sa.Column("status", sa.String(), nullable=False, server_default="draft"),
        sa.Column("reserved_until", sa.DateTime(), nullable=True),
        sa.Column("received_qty", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["order_product_link_id"], ["order_product_link.id"]),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(["request_id"], ["supply_request.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_supply_request_line_request_id", "supply_request_line", ["request_id"], unique=False)
    op.create_index("ix_supply_request_line_order_product_link_id", "supply_request_line", ["order_product_link_id"], unique=False)
    op.create_index("ix_supply_request_line_source_type", "supply_request_line", ["source_type"], unique=False)
    op.create_index("ix_supply_request_line_product_id", "supply_request_line", ["product_id"], unique=False)
    op.create_index("ix_supply_request_line_supplier_offer_external_id", "supply_request_line", ["supplier_offer_external_id"], unique=False)
    op.create_index("ix_supply_request_line_status", "supply_request_line", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_supply_request_line_status", table_name="supply_request_line")
    op.drop_index("ix_supply_request_line_supplier_offer_external_id", table_name="supply_request_line")
    op.drop_index("ix_supply_request_line_product_id", table_name="supply_request_line")
    op.drop_index("ix_supply_request_line_source_type", table_name="supply_request_line")
    op.drop_index("ix_supply_request_line_order_product_link_id", table_name="supply_request_line")
    op.drop_index("ix_supply_request_line_request_id", table_name="supply_request_line")
    op.drop_table("supply_request_line")

    op.drop_index("ix_supply_request_created_at", table_name="supply_request")
    op.drop_index("ix_supply_request_created_by", table_name="supply_request")
    op.drop_index("ix_supply_request_payment_method", table_name="supply_request")
    op.drop_index("ix_supply_request_intent", table_name="supply_request")
    op.drop_index("ix_supply_request_status", table_name="supply_request")
    op.drop_index("ix_supply_request_logistics_contact_id", table_name="supply_request")
    op.drop_index("ix_supply_request_supplier_contact_id", table_name="supply_request")
    op.drop_index("ix_supply_request_warehouse_id", table_name="supply_request")
    op.drop_index("ix_supply_request_supplier_id", table_name="supply_request")
    op.drop_table("supply_request")

    op.drop_index("ix_supplier_warehouse_is_default", table_name="supplier_warehouse")
    op.drop_index("ix_supplier_warehouse_contact_id", table_name="supplier_warehouse")
    op.drop_index("ix_supplier_warehouse_supplier_id", table_name="supplier_warehouse")
    op.drop_table("supplier_warehouse")

    op.drop_index("ix_supplier_contact_default_for_logistics", table_name="supplier_contact")
    op.drop_index("ix_supplier_contact_default_for_orders", table_name="supplier_contact")
    op.drop_index("ix_supplier_contact_supplier_id", table_name="supplier_contact")
    op.drop_table("supplier_contact")

    op.drop_index("ix_supplier_tax_id", table_name="supplier")
    op.drop_column("supplier", "payment_comment")
    op.drop_column("supplier", "default_payment_method")
    op.drop_column("supplier", "postal_address")
    op.drop_column("supplier", "legal_address")
    op.drop_column("supplier", "tax_id")
    op.drop_column("supplier", "legal_name")
