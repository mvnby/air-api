from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Integer,
)
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StorefrontCatalogRevision(SQLModel, table=True):
    """Monotonic catalog revision owned by one exact storefront."""

    __tablename__ = "storefront_catalog_revision"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_storefront_catalog_revision_storefront_tenant",
        ),
        CheckConstraint(
            "revision >= 0",
            name="ck_storefront_catalog_revision_non_negative",
        ),
    )

    tenant_id: int = Field(
        foreign_key="tenant.id",
        primary_key=True,
        nullable=False,
    )
    storefront_id: int = Field(
        sa_column=Column(Integer, primary_key=True, nullable=False),
    )
    revision: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
