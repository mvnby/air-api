from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, Column, DateTime, ForeignKeyConstraint, Integer, String, UniqueConstraint
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class YandexBusinessFeedSettings(SQLModel, table=True):
    """One Yandex Business feed policy for each tenant/storefront scope."""

    __tablename__ = "yandex_business_feed_settings"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "storefront_id",
            name="uq_yandex_business_feed_settings_scope",
        ),
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_yandex_business_feed_settings_storefront_tenant",
        ),
        CheckConstraint(
            "selection_mode IN ('all_published', 'curated_collections')",
            name="ck_yandex_business_feed_settings_selection_mode",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    storefront_id: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    selection_mode: str = Field(
        default="all_published",
        sa_column=Column(String(32), nullable=False, server_default="all_published"),
    )
    include_services: bool = Field(
        default=True,
        sa_column=Column(Boolean, nullable=False, server_default="true"),
    )
    require_ready_image: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    require_in_stock: bool = Field(
        default=False,
        sa_column=Column(Boolean, nullable=False, server_default="false"),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
