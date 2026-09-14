from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, Integer, JSON, String
from sqlmodel import Field, SQLModel

from models.tenancy import utc_now


class StorefrontSettings(SQLModel, table=True):
    """Public identity and service publication, owned by an exact storefront."""

    __tablename__ = "storefront_settings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_storefront_settings_scope",
        ),
    )

    storefront_id: int = Field(primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    display_name: str = Field(sa_column=Column(String(160), nullable=False))
    city: str = Field(default="", sa_column=Column(String(120), nullable=False))
    phone: str = Field(default="", sa_column=Column(String(80), nullable=False))
    email: str = Field(default="", sa_column=Column(String(254), nullable=False))
    address: str = Field(default="", sa_column=Column(String(500), nullable=False))
    work_hours: str = Field(default="", sa_column=Column(String(300), nullable=False))
    support_telegram_url: str = Field(default="", sa_column=Column(String(300), nullable=False))
    services: list[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    version: int = Field(default=1, sa_column=Column(Integer, nullable=False))
    updated_at: datetime = Field(default_factory=utc_now, sa_column=Column(DateTime(timezone=True), nullable=False))
