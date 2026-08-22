from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

from models.tenancy import utc_now


class AnalyticsConnection(SQLModel, table=True):
    """Encrypted analytics credentials bound to one exact storefront."""

    __tablename__ = "analytics_connection"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_analytics_connection_storefront_tenant",
            ondelete="CASCADE",
        ),
        UniqueConstraint(
            "tenant_id",
            "storefront_id",
            "provider",
            name="uq_analytics_connection_scope_provider",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_analytics_connection_status_valid",
        ),
        Index(
            "ix_analytics_connection_scope",
            "tenant_id",
            "storefront_id",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)
    storefront_id: int = Field(sa_column=Column(Integer, nullable=False))
    provider: str = Field(sa_column=Column(String(48), nullable=False))
    status: str = Field(
        default="active",
        sa_column=Column(String(24), nullable=False),
    )
    public_config: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    encrypted_credentials: str = Field(sa_column=Column(Text, nullable=False))
    credentials_fingerprint: str = Field(
        sa_column=Column(String(64), nullable=False),
    )
    last_verified_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_error_code: Optional[str] = Field(
        default=None,
        sa_column=Column(String(80), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
