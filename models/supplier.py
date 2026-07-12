from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, JSON, Numeric, String, Text, UniqueConstraint
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
    legal_name: Optional[str] = Field(default=None)
    tax_id: Optional[str] = Field(default=None, index=True)
    legal_address: Optional[str] = Field(default=None)
    postal_address: Optional[str] = Field(default=None)
    default_payment_method: str = Field(
        default="unknown",
        sa_column=Column(String, default="unknown", nullable=False),
    )
    payment_comment: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    sources: list["SupplierPriceSource"] = Relationship(back_populates="supplier")
    offers: list["SupplierOffer"] = Relationship(back_populates="supplier")
    contacts: list["SupplierContact"] = Relationship(back_populates="supplier")
    warehouses: list["SupplierWarehouse"] = Relationship(back_populates="supplier")
    supply_requests: list["SupplyRequest"] = Relationship(back_populates="supplier")


class SupplierContact(SQLModel, table=True):
    __tablename__ = "supplier_contact"

    id: Optional[int] = Field(default=None, primary_key=True)
    supplier_id: int = Field(foreign_key="supplier.id", index=True)
    name: str
    role: Optional[str] = Field(default=None)
    phone: Optional[str] = Field(default=None)
    viber: Optional[str] = Field(default=None)
    telegram_username: Optional[str] = Field(default=None)
    telegram_chat_id: Optional[str] = Field(default=None)
    email: Optional[str] = Field(default=None)
    preferred_channel: str = Field(default="phone", sa_column=Column(String, default="phone", nullable=False))
    default_for_orders: bool = Field(default=False, index=True)
    default_for_logistics: bool = Field(default=False, index=True)
    comment: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    supplier: "Supplier" = Relationship(back_populates="contacts")


class SupplierWarehouse(SQLModel, table=True):
    __tablename__ = "supplier_warehouse"

    id: Optional[int] = Field(default=None, primary_key=True)
    supplier_id: int = Field(foreign_key="supplier.id", index=True)
    name: str
    address: str = Field(sa_column=Column(Text, nullable=False))
    contact_id: Optional[int] = Field(default=None, foreign_key="supplier_contact.id", index=True)
    contact_name: Optional[str] = Field(default=None)
    contact_phone: Optional[str] = Field(default=None)
    work_hours: Optional[str] = Field(default=None)
    pickup_notes: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    is_default: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    supplier: "Supplier" = Relationship(back_populates="warehouses")
    contact: Optional["SupplierContact"] = Relationship()
    supply_requests: list["SupplyRequest"] = Relationship(back_populates="warehouse")


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
    col_source_url: Optional[str] = Field(default=None)

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
    source_id: Optional[int] = Field(
        default=None,
        foreign_key="supplier_price_source.id",
        ondelete="SET NULL",
        index=True,
    )
    external_id: str = Field(index=True)

    title_raw: Optional[str] = None
    title_normalized: Optional[str] = Field(default=None, index=True)
    model_tokens: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    indoor_model_tokens: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    outdoor_model_tokens: list[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    match_normalizer_version: Optional[str] = Field(default=None, index=True)
    source_url: Optional[str] = Field(default=None, index=True)
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


class SupplyRequest(SQLModel, table=True):
    __tablename__ = "supply_request"

    id: Optional[int] = Field(default=None, primary_key=True)
    supplier_id: int = Field(foreign_key="supplier.id", index=True)
    warehouse_id: Optional[int] = Field(default=None, foreign_key="supplier_warehouse.id", index=True)
    supplier_contact_id: Optional[int] = Field(default=None, foreign_key="supplier_contact.id", index=True)
    logistics_contact_id: Optional[int] = Field(default=None, foreign_key="supplier_contact.id", index=True)
    status: str = Field(default="draft", sa_column=Column(String, default="draft", nullable=False, index=True))
    intent: str = Field(default="order", sa_column=Column(String, default="order", nullable=False, index=True))
    payment_method: str = Field(default="unknown", sa_column=Column(String, default="unknown", nullable=False, index=True))
    comment: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    supplier_message_snapshot: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    logistics_message_snapshot: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_by: Optional[str] = Field(default=None, index=True)
    supplier_message_sent_at: Optional[datetime] = None
    logistics_message_sent_at: Optional[datetime] = None
    created_at: datetime = Field(default_factory=datetime.now, index=True)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    supplier: "Supplier" = Relationship(back_populates="supply_requests")
    warehouse: Optional["SupplierWarehouse"] = Relationship(back_populates="supply_requests")
    supplier_contact: Optional["SupplierContact"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "SupplyRequest.supplier_contact_id"}
    )
    logistics_contact: Optional["SupplierContact"] = Relationship(
        sa_relationship_kwargs={"foreign_keys": "SupplyRequest.logistics_contact_id"}
    )
    lines: list["SupplyRequestLine"] = Relationship(
        back_populates="request",
        sa_relationship_kwargs={"cascade": "all, delete-orphan"},
    )


class SupplyRequestLine(SQLModel, table=True):
    __tablename__ = "supply_request_line"

    id: Optional[int] = Field(default=None, primary_key=True)
    request_id: int = Field(foreign_key="supply_request.id", index=True)
    order_product_link_id: Optional[int] = Field(default=None, foreign_key="order_product_link.id", index=True)
    source_type: str = Field(default="manual", sa_column=Column(String, default="manual", nullable=False, index=True))
    product_id: Optional[int] = Field(default=None, foreign_key="product.id", index=True)
    supplier_offer_external_id: Optional[str] = Field(default=None, index=True)
    supplier_offer_title: Optional[str] = Field(default=None)
    title_snapshot: str
    qty: int = Field(default=1)
    unit_cost_snapshot: Optional[Decimal] = Field(
        default=None,
        sa_column=Column(Numeric(12, 2), nullable=True),
    )
    status: str = Field(default="draft", sa_column=Column(String, default="draft", nullable=False, index=True))
    reserved_until: Optional[datetime] = None
    received_qty: int = Field(default=0)
    comment: Optional[str] = Field(default=None, sa_column=Column(Text, nullable=True))
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    request: "SupplyRequest" = Relationship(back_populates="lines")
    product: Optional["Product"] = Relationship()
    order_product_link: Optional["OrderProductLink"] = Relationship()


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
