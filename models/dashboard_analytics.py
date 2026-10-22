"""Durable, per-source dashboard cache. No credentials or personal data."""
from datetime import date, datetime
from typing import Any

from sqlalchemy import Column, Date, DateTime, ForeignKeyConstraint, Index, Integer, JSON, String
from sqlmodel import Field, SQLModel


class DashboardAnalyticsSnapshot(SQLModel, table=True):
    __tablename__ = "dashboard_analytics_snapshot"
    __table_args__ = (
        ForeignKeyConstraint(["storefront_id", "tenant_id"], ["storefront.id", "storefront.tenant_id"], ondelete="CASCADE"),
        Index("ix_dashboard_snapshot_scope_source", "tenant_id", "storefront_id", "provider", "configuration_revision", "period_start", "period_end"),
    )
    key: str = Field(sa_column=Column(String(64), primary_key=True))
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)
    storefront_id: int = Field(sa_column=Column(Integer, nullable=False))
    provider: str = Field(sa_column=Column(String(48), nullable=False))
    configuration_revision: str = Field(sa_column=Column(String(64), nullable=False))
    schema_version: int = Field(default=1, nullable=False)
    period_start: date = Field(sa_column=Column(Date, nullable=False))
    period_end: date = Field(sa_column=Column(Date, nullable=False))
    payload: dict[str, Any] | None = Field(default=None, sa_column=Column(JSON, nullable=True))
    last_success_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    last_attempt_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    next_retry_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    error_code: str | None = Field(default=None, sa_column=Column(String(80)))
    failure_count: int = Field(default=0, nullable=False)
    lease_token: str | None = Field(default=None, sa_column=Column(String(32)))
    lease_until: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
