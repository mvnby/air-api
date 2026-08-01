from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, Index, String, UniqueConstraint, text
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TenantScope:
    """Server-resolved tenant/storefront pair passed across write boundaries."""

    tenant_id: int
    storefront_id: int
    # Transitional legacy rows belong only to the canonical system tenant.
    # New tenants must never be allowed to claim nullable MVN-era ownership.
    is_system: bool = False
    # Public resolvers set this explicitly. ``None`` keeps compatibility for
    # older internal callers that construct a scope from IDs only.
    is_canonical_storefront: bool | None = None


class Tenant(SQLModel, table=True):
    __tablename__ = "tenant"
    __table_args__ = (
        UniqueConstraint("slug", name="uq_tenant_slug"),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_tenant_status_valid",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(sa_column=Column(String(64), nullable=False))
    display_name: str = Field(sa_column=Column(String(160), nullable=False))
    kind: str = Field(default="independent_seller", sa_column=Column(String(40), nullable=False, index=True))
    status: str = Field(default="active", sa_column=Column(String(24), nullable=False, index=True))
    is_system: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class TenantMembership(SQLModel, table=True):
    __tablename__ = "tenant_membership"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "staff_user_id",
            name="uq_tenant_membership_tenant_staff_user",
        ),
        CheckConstraint(
            "status IN ('active', 'suspended', 'disabled')",
            name="ck_tenant_membership_status_valid",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    staff_user_id: int = Field(foreign_key="staff_users.id", index=True)
    role: str = Field(sa_column=Column(String(40), nullable=False, index=True))
    status: str = Field(default="active", sa_column=Column(String(24), nullable=False, index=True))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class Storefront(SQLModel, table=True):
    __tablename__ = "storefront"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_storefront_id_tenant"),
        UniqueConstraint("tenant_id", "slug", name="uq_storefront_tenant_slug"),
        Index(
            "uq_storefront_default_per_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_default"),
            sqlite_where=text("is_default = 1"),
        ),
        CheckConstraint(
            "status IN ('draft', 'active', 'disabled')",
            name="ck_storefront_status_valid",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    slug: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    display_name: str = Field(sa_column=Column(String(160), nullable=False))
    status: str = Field(default="draft", sa_column=Column(String(24), nullable=False, index=True))
    city: Optional[str] = Field(default=None, sa_column=Column(String(120), nullable=True, index=True))
    default_locale: str = Field(default="ru-BY", sa_column=Column(String(16), nullable=False))
    currency: str = Field(default="BYN", sa_column=Column(String(3), nullable=False))
    is_default: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class StorefrontDomain(SQLModel, table=True):
    __tablename__ = "storefront_domain"
    __table_args__ = (
        UniqueConstraint("hostname", name="uq_storefront_domain_hostname"),
        Index(
            "uq_storefront_primary_domain",
            "storefront_id",
            unique=True,
            postgresql_where=text("is_primary"),
            sqlite_where=text("is_primary = 1"),
        ),
        CheckConstraint(
            "status IN ('pending', 'active', 'disabled')",
            name="ck_storefront_domain_status_valid",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    storefront_id: int = Field(foreign_key="storefront.id", index=True)
    hostname: str = Field(sa_column=Column(String(253), nullable=False))
    status: str = Field(default="pending", sa_column=Column(String(24), nullable=False, index=True))
    is_primary: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    verified_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
