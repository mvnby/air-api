"""Tenant-owned service dictionaries, tariffs and saved estimate snapshots."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, DateTime, Index, JSON, Numeric, Text, UniqueConstraint, text
from sqlmodel import Field, Relationship, SQLModel


class Service(SQLModel, table=True):
    __table_args__ = (
        UniqueConstraint("tenant_id", "slug", name="uq_service_tenant_slug"),
        Index(
            "uq_service_canonical_slug",
            "slug",
            unique=True,
            postgresql_where=text("tenant_id IS NULL"),
            sqlite_where=text("tenant_id IS NULL"),
        ),
        Index(
            "uq_service_tenant_source",
            "tenant_id",
            "source_service_id",
            unique=True,
            postgresql_where=text(
                "tenant_id IS NOT NULL AND source_service_id IS NOT NULL"
            ),
            sqlite_where=text(
                "tenant_id IS NOT NULL AND source_service_id IS NOT NULL"
            ),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)
    source_service_id: Optional[int] = Field(
        default=None,
        foreign_key="service.id",
        ondelete="SET NULL",
        index=True,
    )
    title: str = Field(index=True)
    slug: str = Field(index=True)
    category: str = Field(default="installation_option", index=True)
    is_active: bool = Field(default=True)
    image: Optional[str] = None
    description: Optional[str] = None
    base_price: int = Field(default=0)

    order_links: List["OrderServiceLink"] = Relationship(back_populates="service")

    @property
    def image_file(self) -> Any:
        return getattr(self, "_temp_image_file", None)

    @image_file.setter
    def image_file(self, value: Any):
        self._temp_image_file = value

    def __str__(self):
        return f"{self.title} ({self.base_price} руб.)"


class ServiceTariff(SQLModel, table=True):
    __tablename__ = "service_tariff"
    __table_args__ = (
        Index(
            "uq_service_tariff_tenant_source",
            "tenant_id",
            "source_tariff_id",
            unique=True,
            postgresql_where=text(
                "tenant_id IS NOT NULL AND source_tariff_id IS NOT NULL"
            ),
            sqlite_where=text(
                "tenant_id IS NOT NULL AND source_tariff_id IS NOT NULL"
            ),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)
    source_tariff_id: Optional[int] = Field(
        default=None,
        foreign_key="service_tariff.id",
        ondelete="SET NULL",
        index=True,
    )
    service_kind: str = Field(default="installation", index=True)
    selector_label: str = Field(index=True)
    estimate_template: str = Field(
        default="Монтаж кондиционера, включая расходные материалы"
    )
    short_name: Optional[str] = Field(default=None, index=True)
    full_description: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    category: str = Field(default="", index=True)
    power_range: str = Field(default="", index=True)
    base_price: int = Field(default=0)
    # Mutable Manager draft; only an explicit price-book publication exposes it
    # through the installation resolver. Legacy tariffs have no matcher.
    installation_match: Optional[Dict[str, Any]] = Field(default=None, sa_column=Column(JSON))
    installation_code: Optional[str] = Field(default=None, index=True)
    installation_price_mode: str = Field(default="fixed")
    included_holes_by_type: Dict[str, Any] = Field(default_factory=dict, sa_column=Column(JSON, nullable=False))
    included_route_meters: float = Field(default=3.0)
    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)
    comment: Optional[str] = Field(default=None)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )
    rules: List["ServiceTariffRule"] = Relationship(
        back_populates="tariff",
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin",
            "order_by": lambda: (
                ServiceTariffRule.sort_order,
                ServiceTariffRule.id,
            ),
        },
    )

    @property
    def effective_short_name(self) -> str:
        return (self.short_name or self.selector_label or "").strip()

    @property
    def effective_full_description(self) -> str:
        return (
            self.full_description or self.estimate_template or self.effective_short_name
        ).strip()


class ServiceTariffRule(SQLModel, table=True):
    __tablename__ = "service_tariff_rule"
    __table_args__ = (
        UniqueConstraint(
            "tariff_id",
            "source_rule_id",
            name="uq_service_tariff_rule_parent_source",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    source_rule_id: Optional[int] = Field(
        default=None,
        foreign_key="service_tariff_rule.id",
        ondelete="SET NULL",
        index=True,
    )
    tariff_id: int = Field(
        foreign_key="service_tariff.id",
        ondelete="CASCADE",
        index=True,
    )
    rule_type: str = Field(default="per_unit_manual", index=True)
    name: str = Field(index=True)
    line_template: str = Field(default="{name}")
    unit: str = Field(default="шт")
    unit_price: float = Field(default=0.0)
    component_code: Optional[str] = Field(default=None, index=True)
    is_optional: bool = Field(default=False, index=True)
    is_favorite: bool = Field(default=False, index=True)
    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)
    service_id: Optional[int] = Field(
        default=None,
        foreign_key="service.id",
        ondelete="SET NULL",
        index=True,
    )
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: Optional[datetime] = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )
    tariff: "ServiceTariff" = Relationship(back_populates="rules")
    service: Optional["Service"] = Relationship()


class InstallationPriceBook(SQLModel, table=True):
    """Immutable published copy of one tenant's installation draft."""

    __tablename__ = "installation_price_book"
    __table_args__ = (UniqueConstraint("tenant_id", "revision", name="uq_installation_book_tenant_revision"),)

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    revision: int = Field(index=True)
    fingerprint: str = Field(index=True)
    entries: List[Dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    published_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    published_by: Optional[str] = None


class InstallationPreviewSnapshot(SQLModel, table=True):
    """Private, scope-bound preview; the bearer token is stored only as a hash."""

    __tablename__ = "installation_preview_snapshot"
    __table_args__ = (
        UniqueConstraint("tenant_id", "storefront_id", "key_hash", name="uq_installation_preview_scope_key"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    token_hash: str = Field(unique=True, index=True)
    key_hash: str = Field(index=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    storefront_id: int = Field(foreign_key="storefront.id", index=True)
    price_book_id: int = Field(foreign_key="installation_price_book.id", index=True)
    input_hash: str
    snapshot: Dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False))
    expires_at: datetime = Field(sa_column=Column(DateTime(timezone=True), nullable=False, index=True))


class ServiceEstimate(SQLModel, table=True):
    __tablename__ = "service_estimate"
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: Optional[int] = Field(default=None, foreign_key="tenant.id", index=True)
    customer_id: Optional[int] = Field(
        default=None,
        foreign_key="customer.id",
        ondelete="SET NULL",
        index=True,
    )
    tariff_id: Optional[int] = Field(
        default=None,
        foreign_key="service_tariff.id",
        ondelete="SET NULL",
        index=True,
    )
    title: str = Field(default="Смета услуг")
    comment: Optional[str] = Field(default=None)
    service_kind: str = Field(default="installation", index=True)
    currency: str = Field(default="BYN")
    subtotal: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(), nullable=False))
    discount_amount: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(), nullable=False))
    total: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(), nullable=False))
    calculation_payload: Optional[Dict[str, Any]] = Field(
        default=None, sa_column=Column(JSON)
    )
    status: str = Field(default="draft", index=True)
    created_by: Optional[str] = Field(default=None, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    customer: Optional["Customer"] = Relationship()
    tariff: Optional["ServiceTariff"] = Relationship()
    items: List["ServiceEstimateItem"] = Relationship(
        back_populates="estimate",
        sa_relationship_kwargs={"cascade": "all, delete-orphan", "lazy": "selectin"},
    )


class ServiceEstimateItem(SQLModel, table=True):
    __tablename__ = "service_estimate_item"
    id: Optional[int] = Field(default=None, primary_key=True)
    estimate_id: int = Field(
        foreign_key="service_estimate.id",
        ondelete="CASCADE",
        index=True,
    )
    source_type: str = Field(default="base", index=True)
    source_id: Optional[int] = Field(default=None)
    service_id: Optional[int] = Field(
        default=None,
        foreign_key="service.id",
        ondelete="SET NULL",
        index=True,
    )
    name: str
    short_name: Optional[str] = Field(default=None)
    full_description: Optional[str] = Field(
        default=None, sa_column=Column(Text, nullable=True)
    )
    qty: float = Field(default=1.0)
    unit: str = Field(default="шт")
    unit_price: float = Field(default=0.0)
    line_total: Decimal = Field(default=Decimal("0.00"), sa_column=Column(Numeric(), nullable=False))
    sort_order: int = Field(default=0)
    estimate: ServiceEstimate = Relationship(back_populates="items")
