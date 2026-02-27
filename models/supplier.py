from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, Numeric, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class Supplier(SQLModel, table=True):
    __tablename__ = "supplier"

    id: Optional[int] = Field(default=None, primary_key=True)
    name: str = Field(index=True)
    code: str = Field(unique=True, index=True)
    is_active: bool = Field(default=True, index=True)
    priority: int = Field(default=100, index=True)
    spreadsheet_id: Optional[str] = Field(default=None, index=True)
    spreadsheet_url: Optional[str] = Field(default=None)
    google_sheet_synced_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    sources: list["SupplierPriceSource"] = Relationship(back_populates="supplier")
    offers: list["SupplierOffer"] = Relationship(back_populates="supplier")


class SupplierPriceSource(SQLModel, table=True):
    __tablename__ = "supplier_price_source"

    id: Optional[int] = Field(default=None, primary_key=True)
    supplier_id: int = Field(foreign_key="supplier.id", index=True)

    source_type: str = Field(default="google_sheet", index=True)
    spreadsheet_id: Optional[str] = Field(default=None, index=True)
    sheet_name: Optional[str] = Field(default=None)
    range_a1: Optional[str] = Field(default=None)
    city_bucket: str = Field(default="minsk", index=True)
    header_row_index: int = Field(default=1)

    col_external_id: str = Field(default="A")
    col_title: str = Field(default="B")
    col_wholesale: str = Field(default="C")
    col_wholesale_currency: str = Field(default="D")
    col_rrc_byn: str = Field(default="E")
    col_qty: str = Field(default="F")

    is_active: bool = Field(default=True, index=True)
    last_sync_at: Optional[datetime] = None
    last_sync_status: Optional[str] = Field(default=None, index=True)
    last_sync_error: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    supplier: "Supplier" = Relationship(back_populates="sources")
    sync_runs: list["SupplierSyncRun"] = Relationship(back_populates="source")


class SupplierOffer(SQLModel, table=True):
    __tablename__ = "supplier_offer"
    __table_args__ = (UniqueConstraint("supplier_id", "external_id", name="uq_supplier_offer_key"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    supplier_id: int = Field(foreign_key="supplier.id", index=True)
    source_id: Optional[int] = Field(default=None, foreign_key="supplier_price_source.id", index=True)
    external_id: str = Field(index=True)

    title_raw: Optional[str] = None
    qty_raw: Optional[str] = None
    wholesale_raw: Optional[str] = None
    rrc_raw: Optional[str] = None

    qty: int = Field(default=0, index=True)
    wholesale_value: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 2), nullable=True),
    )
    wholesale_currency: Optional[str] = Field(default=None, index=True)
    rrc_byn: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 2), nullable=True),
    )

    is_active: bool = Field(default=True, index=True)
    last_seen_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    supplier: "Supplier" = Relationship(back_populates="offers")
    product_mappings: list["ProductSupplierMapping"] = Relationship(back_populates="offer")


class ProductSupplierMapping(SQLModel, table=True):
    __tablename__ = "product_supplier_mapping"
    __table_args__ = (
        UniqueConstraint("product_id", "supplier_id", "external_id", name="uq_product_supplier_mapping"),
        UniqueConstraint("supplier_id", "external_id", name="uq_supplier_external_unique_mapping"),
        ForeignKeyConstraint(
            ["supplier_id", "external_id"],
            ["supplier_offer.supplier_id", "supplier_offer.external_id"],
            name="fk_product_supplier_mapping_offer",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    supplier_id: int = Field(index=True)
    external_id: str = Field(index=True)
    is_active: bool = Field(default=True, index=True)
    mapped_by: Optional[str] = None
    mapped_at: datetime = Field(default_factory=datetime.now, sa_column=Column(DateTime, nullable=False))

    product: "Product" = Relationship(back_populates="supplier_mappings")
    offer: Optional["SupplierOffer"] = Relationship(back_populates="product_mappings")


class ProductLocalStock(SQLModel, table=True):
    __tablename__ = "product_local_stock"
    __table_args__ = (UniqueConstraint("product_id", "warehouse_code", name="uq_product_warehouse"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    warehouse_code: str = Field(default="vitebsk", index=True)
    qty: int = Field(default=0)
    updated_by: Optional[str] = None
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    product: "Product" = Relationship(back_populates="local_stocks")


class SupplierSyncRun(SQLModel, table=True):
    __tablename__ = "supplier_sync_run"

    id: Optional[int] = Field(default=None, primary_key=True)
    source_id: int = Field(foreign_key="supplier_price_source.id", index=True)
    started_at: datetime = Field(default_factory=datetime.now)
    finished_at: Optional[datetime] = None
    status: str = Field(default="running", index=True)
    rows_total: int = Field(default=0)
    rows_upserted: int = Field(default=0)
    rows_skipped: int = Field(default=0)
    rows_deactivated: int = Field(default=0)
    error: Optional[str] = None

    source: "SupplierPriceSource" = Relationship(back_populates="sync_runs")
