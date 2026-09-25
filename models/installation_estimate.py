"""Durable, immutable confirmed installation estimate revisions."""

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, JSON, Numeric, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class InstallationEstimate(SQLModel, table=True):
    __tablename__ = "installation_estimate"
    __table_args__ = (
        UniqueConstraint("tenant_id", "storefront_id", "confirmation_key_hash",
                         name="uq_installation_estimate_scope_key"),
        UniqueConstraint("tenant_id", "storefront_id", "preview_token_hash", "order_id", "proposal_id",
                         name="uq_installation_estimate_preview_target"),
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"], ["storefront.id", "storefront.tenant_id"],
            name="fk_installation_estimate_storefront_tenant",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    storefront_id: int = Field(index=True)
    order_id: int = Field(foreign_key="order.id", index=True)
    proposal_id: int = Field(foreign_key="order_proposal.id", index=True)
    confirmation_key_hash: str = Field(index=True)
    confirmation_request_hash: str
    preview_token_hash: str = Field(index=True)
    status: str = Field(default="accepted")
    created_by: str | None = None
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))


class InstallationEstimateRevision(SQLModel, table=True):
    __tablename__ = "installation_estimate_revision"
    __table_args__ = (
        UniqueConstraint("estimate_id", "revision", name="uq_installation_estimate_revision"),
    )

    id: int | None = Field(default=None, primary_key=True)
    estimate_id: int = Field(foreign_key="installation_estimate.id", index=True)
    revision: int = Field(default=1)
    price_book_id: int = Field(foreign_key="installation_price_book.id", index=True)
    price_book_revision: int
    total: Decimal = Field(sa_column=Column(Numeric(14, 2), nullable=False))
    snapshot: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    created_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
