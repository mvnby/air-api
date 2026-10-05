"""System Jev connection and durable, non-authoritative classification samples."""
from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy import CheckConstraint, Column, Date, DateTime, ForeignKeyConstraint, Numeric, String, Text, UniqueConstraint
from sqlmodel import Field, SQLModel


class JevConnection(SQLModel, table=True):
    __tablename__ = "jev_connection"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_jev_connection_singleton"),
        CheckConstraint("(encrypted_credentials IS NULL) = (credentials_fingerprint IS NULL)", name="ck_jev_connection_key_pair"),
        CheckConstraint("NOT enabled OR encrypted_credentials IS NOT NULL", name="ck_jev_connection_enabled_key"),
        CheckConstraint("daily_budget_usd > 0 AND daily_budget_usd <= 5", name="ck_jev_connection_budget"),
    )
    id: int = Field(default=1, primary_key=True)
    encrypted_credentials: str | None = Field(default=None, sa_column=Column(Text))
    credentials_fingerprint: str | None = Field(default=None, sa_column=Column(String(64)))
    enabled: bool = Field(default=False, nullable=False)
    daily_budget_usd: Decimal = Field(default=Decimal("0.05"), sa_column=Column(Numeric(12, 8), nullable=False))
    budget_day: date | None = Field(default=None, sa_column=Column(Date))
    budget_used_usd: Decimal = Field(default=Decimal("0"), sa_column=Column(Numeric(12, 8), nullable=False))
    daily_requests: int = Field(default=0, nullable=False)


class JevShadowSample(SQLModel, table=True):
    __tablename__ = "jev_shadow_sample"
    __table_args__ = (
        ForeignKeyConstraint(["storefront_id", "tenant_id"], ["storefront.id", "storefront.tenant_id"], name="fk_jev_shadow_scope"),
        UniqueConstraint("tenant_id", "storefront_id", "source", "sample_key", name="uq_jev_shadow_sample"),
        CheckConstraint("source IN ('email', 'belzakupki')", name="ck_jev_shadow_source"),
        CheckConstraint("status IN ('queued', 'running', 'completed', 'failed')", name="ck_jev_shadow_status"),
    )
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    storefront_id: int = Field(nullable=False)
    source: str = Field(sa_column=Column(String(24), nullable=False))
    sample_key: str = Field(sa_column=Column(String(64), nullable=False))
    subject: str = Field(sa_column=Column(String(500), nullable=False))
    state: str = Field(sa_column=Column(Text, nullable=False))
    prompt_version: str = Field(default="intake-v1", sa_column=Column(String(32), nullable=False))
    status: str = Field(default="queued", sa_column=Column(String(24), nullable=False, index=True))
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc), sa_column=Column(DateTime(timezone=True), nullable=False, index=True))
    started_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))
    budget_day: date | None = Field(default=None, sa_column=Column(Date))
    primary_provider: str = Field(sa_column=Column(String(32), nullable=False))
    primary_model_requested: str | None = Field(default=None, sa_column=Column(String(160)))
    primary_is_relevant: bool | None = None
    primary_duration_ms: int | None = None
    model: str | None = Field(default=None, sa_column=Column(String(80)))
    kind: str | None = Field(default=None, sa_column=Column(String(32)))
    kind_confidence: float | None = None
    hvac_probability: float | None = None
    jev_is_relevant: bool | None = None
    input_tokens: int | None = None
    duration_ms: int | None = None
    estimated_usd: Decimal | None = Field(default=None, sa_column=Column(Numeric(12, 8)))
    error_code: str | None = Field(default=None, sa_column=Column(String(64)))
