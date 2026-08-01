from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TenantOffer(SQLModel, table=True):
    """Storefront-owned commercial projection of a shared catalog product."""

    __tablename__ = "tenant_offer"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "storefront_id",
            "product_id",
            name="uq_tenant_offer_scope_product",
        ),
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_tenant_offer_storefront_tenant",
        ),
        CheckConstraint("price >= 0", name="ck_tenant_offer_price_non_negative"),
        CheckConstraint(
            "old_price IS NULL OR old_price >= price",
            name="ck_tenant_offer_old_price_valid",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_tenant_offer_status_valid",
        ),
        Index(
            "ix_tenant_offer_scope_visibility",
            "tenant_id",
            "storefront_id",
            "status",
            "is_published",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)
    storefront_id: int = Field(sa_column=Column(Integer, nullable=False))
    product_id: int = Field(foreign_key="product.id", nullable=False, index=True)
    price: int = Field(sa_column=Column(Integer, nullable=False))
    old_price: Optional[int] = Field(default=None, sa_column=Column(Integer, nullable=True))
    is_published: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False),
    )
    status: str = Field(
        default="active",
        sa_column=Column(String(24), nullable=False),
    )
    created_by_username: str = Field(
        sa_column=Column(String(160), nullable=False),
    )
    updated_by_username: str = Field(
        sa_column=Column(String(160), nullable=False),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class TenantAuditEvent(SQLModel, table=True):
    """Append-only tenant audit record written in the command transaction."""

    __tablename__ = "tenant_audit_event"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_tenant_audit_storefront_tenant",
        ),
        Index(
            "ix_tenant_audit_scope_created_at",
            "tenant_id",
            "storefront_id",
            "created_at",
        ),
        Index(
            "ix_tenant_audit_scope_entity",
            "tenant_id",
            "storefront_id",
            "entity_type",
            "entity_id",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)
    storefront_id: int = Field(sa_column=Column(Integer, nullable=False))
    actor_staff_user_id: Optional[int] = Field(
        default=None,
        sa_column=Column(Integer, nullable=True),
    )
    actor_username: str = Field(sa_column=Column(String(160), nullable=False))
    action: str = Field(sa_column=Column(String(120), nullable=False))
    entity_type: str = Field(sa_column=Column(String(80), nullable=False))
    entity_id: int = Field(sa_column=Column(Integer, nullable=False))
    request_id: str = Field(sa_column=Column(String(64), nullable=False))
    change_set: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
