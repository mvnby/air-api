from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, Relationship, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ProductCollection(SQLModel, table=True):
    __tablename__ = "product_collection"
    __table_args__ = (
        UniqueConstraint(
            "id",
            "tenant_id",
            "storefront_id",
            name="uq_product_collection_id_scope",
        ),
        UniqueConstraint(
            "tenant_id",
            "storefront_id",
            "slug",
            name="uq_product_collection_scope_slug",
        ),
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_product_collection_storefront_tenant",
        ),
        ForeignKeyConstraint(
            ["fallback_collection_id", "tenant_id", "storefront_id"],
            [
                "product_collection.id",
                "product_collection.tenant_id",
                "product_collection.storefront_id",
            ],
            name="fk_product_collection_fallback_scope",
            deferrable=True,
            initially="DEFERRED",
        ),
        ForeignKeyConstraint(
            ["fallback_collection_id"],
            ["product_collection.id"],
            name="fk_product_collection_fallback_delete",
            ondelete="SET NULL",
        ),
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_product_collection_status",
        ),
        CheckConstraint(
            "mode IN ('manual', 'automatic', 'hybrid')",
            name="ck_product_collection_mode",
        ),
        CheckConstraint(
            "min_items >= 1 AND max_items >= min_items AND max_items <= 24",
            name="ck_product_collection_item_limits",
        ),
        CheckConstraint(
            "sort_mode IN ('recommended', 'price_asc', 'price_desc', 'area_asc', 'area_desc', 'newest')",
            name="ck_product_collection_sort_mode",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    storefront_id: int = Field(
        sa_column=Column(Integer, nullable=False, index=True),
    )
    slug: str = Field(sa_column=Column(String(120), nullable=False, index=True))
    internal_name: str = Field(sa_column=Column(String(180), nullable=False, index=True))
    public_title: str = Field(sa_column=Column(String(180), nullable=False))
    public_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    public_badge: Optional[str] = Field(default=None, sa_column=Column(String(80)))
    cta_label: Optional[str] = Field(default=None, sa_column=Column(String(80)))
    cta_url: Optional[str] = Field(default=None, sa_column=Column(String(500)))
    editorial_note: Optional[str] = Field(default=None, sa_column=Column(Text))
    status: str = Field(default="draft", sa_column=Column(String(24), nullable=False, index=True))
    mode: str = Field(default="manual", sa_column=Column(String(24), nullable=False, index=True))
    sort_mode: str = Field(default="recommended", sa_column=Column(String(32), nullable=False))
    rule_config: dict = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    min_items: int = Field(default=1)
    max_items: int = Field(default=6)
    fallback_collection_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True, index=True),
    )
    starts_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    ends_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )

    items: List["ProductCollectionItem"] = Relationship(back_populates="collection")
    placements: List["ProductCollectionPlacement"] = Relationship(back_populates="collection")


class ProductCollectionItem(SQLModel, table=True):
    __tablename__ = "product_collection_item"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_product_collection_item_storefront_tenant",
        ),
        ForeignKeyConstraint(
            ["collection_id", "tenant_id", "storefront_id"],
            [
                "product_collection.id",
                "product_collection.tenant_id",
                "product_collection.storefront_id",
            ],
            name="fk_product_collection_item_collection_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "storefront_id",
            "collection_id",
            "product_id",
            name="uq_product_collection_item_scope_product",
        ),
        UniqueConstraint(
            "tenant_id",
            "storefront_id",
            "collection_id",
            "position",
            name="uq_product_collection_item_scope_position",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    storefront_id: int = Field(
        sa_column=Column(Integer, nullable=False, index=True),
    )
    collection_id: int = Field(
        sa_column=Column(Integer, nullable=False, index=True),
    )
    product_id: int = Field(
        foreign_key="product.id",
        ondelete="RESTRICT",
        index=True,
    )
    position: int = Field(default=0, index=True)
    is_pinned: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    editorial_note: Optional[str] = Field(default=None, sa_column=Column(Text))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    collection: ProductCollection = Relationship(back_populates="items")
    product: "Product" = Relationship()


class ProductCollectionPlacement(SQLModel, table=True):
    __tablename__ = "product_collection_placement"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_product_collection_placement_storefront_tenant",
        ),
        ForeignKeyConstraint(
            ["collection_id", "tenant_id", "storefront_id"],
            [
                "product_collection.id",
                "product_collection.tenant_id",
                "product_collection.storefront_id",
            ],
            name="fk_product_collection_placement_collection_scope",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "storefront_id",
            "surface_key",
            "slot_key",
            "collection_id",
            name="uq_product_collection_placement_scope_slot",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    storefront_id: int = Field(
        sa_column=Column(Integer, nullable=False, index=True),
    )
    surface_key: str = Field(sa_column=Column(String(80), nullable=False, index=True))
    slot_key: str = Field(sa_column=Column(String(80), nullable=False, index=True))
    collection_id: int = Field(
        sa_column=Column(Integer, nullable=False, index=True),
    )
    position: int = Field(default=0, index=True)
    is_enabled: bool = Field(default=True, sa_column=Column(Boolean, nullable=False, index=True))
    starts_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    ends_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )

    collection: ProductCollection = Relationship(back_populates="placements")
