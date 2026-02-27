"""add_supplier_price_integration

Revision ID: ab12cd34ef56
Revises: 6424bfd28540
Create Date: 2026-02-26 17:15:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import sqlmodel


# revision identifiers, used by Alembic.
revision: str = "ab12cd34ef56"
down_revision: Union[str, Sequence[str], None] = "6424bfd28540"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "supplier",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("code", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("priority", sa.Integer(), nullable=False, server_default=sa.text("100")),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("supplier", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_supplier_code"), ["code"], unique=True)
        batch_op.create_index(batch_op.f("ix_supplier_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_supplier_name"), ["name"], unique=False)
        batch_op.create_index(batch_op.f("ix_supplier_priority"), ["priority"], unique=False)

    op.create_table(
        "supplier_price_source",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("source_type", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="google_sheet"),
        sa.Column("spreadsheet_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("sheet_name", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("range_a1", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("city_bucket", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="minsk"),
        sa.Column("header_row_index", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("col_external_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="A"),
        sa.Column("col_title", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="B"),
        sa.Column("col_wholesale", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="C"),
        sa.Column("col_wholesale_currency", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="D"),
        sa.Column("col_rrc_byn", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="E"),
        sa.Column("col_qty", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="F"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_sync_at", sa.DateTime(), nullable=True),
        sa.Column("last_sync_status", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("last_sync_error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("supplier_price_source", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_supplier_price_source_city_bucket"), ["city_bucket"], unique=False)
        batch_op.create_index(batch_op.f("ix_supplier_price_source_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_supplier_price_source_last_sync_status"), ["last_sync_status"], unique=False)
        batch_op.create_index(batch_op.f("ix_supplier_price_source_source_type"), ["source_type"], unique=False)
        batch_op.create_index(batch_op.f("ix_supplier_price_source_spreadsheet_id"), ["spreadsheet_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_supplier_price_source_supplier_id"), ["supplier_id"], unique=False)

    op.create_table(
        "supplier_offer",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("title_raw", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("qty_raw", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("wholesale_raw", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("rrc_raw", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("qty", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("wholesale_value", sa.Numeric(12, 2), nullable=True),
        sa.Column("wholesale_currency", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("rrc_byn", sa.Numeric(12, 2), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("last_seen_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["supplier_id"], ["supplier.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("supplier_id", "external_id", name="uq_supplier_offer_key"),
    )
    with op.batch_alter_table("supplier_offer", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_supplier_offer_external_id"), ["external_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_supplier_offer_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_supplier_offer_qty"), ["qty"], unique=False)
        batch_op.create_index(batch_op.f("ix_supplier_offer_supplier_id"), ["supplier_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_supplier_offer_wholesale_currency"), ["wholesale_currency"], unique=False)

    op.create_table(
        "product_supplier_mapping",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("supplier_id", sa.Integer(), nullable=False),
        sa.Column("external_id", sqlmodel.sql.sqltypes.AutoString(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("mapped_by", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("mapped_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.ForeignKeyConstraint(
            ["supplier_id", "external_id"],
            ["supplier_offer.supplier_id", "supplier_offer.external_id"],
            name="fk_product_supplier_mapping_offer",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "supplier_id", "external_id", name="uq_product_supplier_mapping"),
        sa.UniqueConstraint("supplier_id", "external_id", name="uq_supplier_external_unique_mapping"),
    )
    with op.batch_alter_table("product_supplier_mapping", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_product_supplier_mapping_external_id"), ["external_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_product_supplier_mapping_is_active"), ["is_active"], unique=False)
        batch_op.create_index(batch_op.f("ix_product_supplier_mapping_product_id"), ["product_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_product_supplier_mapping_supplier_id"), ["supplier_id"], unique=False)

    op.create_table(
        "product_local_stock",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("product_id", sa.Integer(), nullable=False),
        sa.Column("warehouse_code", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="vitebsk"),
        sa.Column("qty", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("updated_by", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["product_id"], ["product.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("product_id", "warehouse_code", name="uq_product_warehouse"),
    )
    with op.batch_alter_table("product_local_stock", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_product_local_stock_product_id"), ["product_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_product_local_stock_warehouse_code"), ["warehouse_code"], unique=False)

    op.create_table(
        "supplier_sync_run",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=False),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("status", sqlmodel.sql.sqltypes.AutoString(), nullable=False, server_default="running"),
        sa.Column("rows_total", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rows_upserted", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rows_skipped", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("rows_deactivated", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("error", sqlmodel.sql.sqltypes.AutoString(), nullable=True),
        sa.ForeignKeyConstraint(["source_id"], ["supplier_price_source.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    with op.batch_alter_table("supplier_sync_run", schema=None) as batch_op:
        batch_op.create_index(batch_op.f("ix_supplier_sync_run_source_id"), ["source_id"], unique=False)
        batch_op.create_index(batch_op.f("ix_supplier_sync_run_status"), ["status"], unique=False)

    op.execute(
        """
        INSERT INTO global_config (key, value, description, updated_at)
        VALUES
        ('fx_rate_usd_byn', '3.25', 'USD -> BYN курс для расчета закупки', NOW()),
        ('supplier_sync_enabled', 'true', 'Включить авто-синк прайсов поставщиков', NOW()),
        ('supplier_sync_interval_minutes', '60', 'Интервал синка поставщиков (мин)', NOW())
        ON CONFLICT (key) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute(
        """
        DELETE FROM global_config
        WHERE key IN ('fx_rate_usd_byn', 'supplier_sync_enabled', 'supplier_sync_interval_minutes')
        """
    )

    with op.batch_alter_table("supplier_sync_run", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_supplier_sync_run_status"))
        batch_op.drop_index(batch_op.f("ix_supplier_sync_run_source_id"))
    op.drop_table("supplier_sync_run")

    with op.batch_alter_table("product_local_stock", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_product_local_stock_warehouse_code"))
        batch_op.drop_index(batch_op.f("ix_product_local_stock_product_id"))
    op.drop_table("product_local_stock")

    with op.batch_alter_table("product_supplier_mapping", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_product_supplier_mapping_supplier_id"))
        batch_op.drop_index(batch_op.f("ix_product_supplier_mapping_product_id"))
        batch_op.drop_index(batch_op.f("ix_product_supplier_mapping_is_active"))
        batch_op.drop_index(batch_op.f("ix_product_supplier_mapping_external_id"))
    op.drop_table("product_supplier_mapping")

    with op.batch_alter_table("supplier_offer", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_supplier_offer_wholesale_currency"))
        batch_op.drop_index(batch_op.f("ix_supplier_offer_supplier_id"))
        batch_op.drop_index(batch_op.f("ix_supplier_offer_qty"))
        batch_op.drop_index(batch_op.f("ix_supplier_offer_is_active"))
        batch_op.drop_index(batch_op.f("ix_supplier_offer_external_id"))
    op.drop_table("supplier_offer")

    with op.batch_alter_table("supplier_price_source", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_supplier_price_source_supplier_id"))
        batch_op.drop_index(batch_op.f("ix_supplier_price_source_spreadsheet_id"))
        batch_op.drop_index(batch_op.f("ix_supplier_price_source_source_type"))
        batch_op.drop_index(batch_op.f("ix_supplier_price_source_last_sync_status"))
        batch_op.drop_index(batch_op.f("ix_supplier_price_source_is_active"))
        batch_op.drop_index(batch_op.f("ix_supplier_price_source_city_bucket"))
    op.drop_table("supplier_price_source")

    with op.batch_alter_table("supplier", schema=None) as batch_op:
        batch_op.drop_index(batch_op.f("ix_supplier_priority"))
        batch_op.drop_index(batch_op.f("ix_supplier_name"))
        batch_op.drop_index(batch_op.f("ix_supplier_is_active"))
        batch_op.drop_index(batch_op.f("ix_supplier_code"))
    op.drop_table("supplier")
