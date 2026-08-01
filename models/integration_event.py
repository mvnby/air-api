from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import CheckConstraint, Column, DateTime, Index, String, UniqueConstraint
from sqlmodel import Field, JSON, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class IntegrationOutboxEvent(SQLModel, table=True):
    __tablename__ = "integration_outbox_event"
    __table_args__ = (
        UniqueConstraint(
            "deduplication_key",
            name="uq_integration_outbox_event_deduplication_key",
        ),
        CheckConstraint("schema_version > 0", name="ck_outbox_schema_version_positive"),
        CheckConstraint("attempts >= 0", name="ck_outbox_attempts_non_negative"),
        CheckConstraint("max_attempts > 0", name="ck_outbox_max_attempts_positive"),
        CheckConstraint(
            "status IN ('pending', 'processing', 'published', 'dead')",
            name="ck_outbox_status_valid",
        ),
        Index(
            "ix_integration_outbox_event_claim",
            "status",
            "available_at",
            "priority",
            "occurred_at",
        ),
        Index(
            "ix_integration_outbox_event_catalog_claim",
            "event_type",
            "status",
            "available_at",
            "priority",
            "occurred_at",
        ),
        Index(
            "ix_integration_outbox_event_aggregate",
            "aggregate_type",
            "aggregate_id",
            "occurred_at",
        ),
    )

    event_id: str = Field(
        sa_column=Column(String(32), primary_key=True),
    )
    event_type: str = Field(sa_column=Column(String(120), nullable=False, index=True))
    schema_version: int = Field(default=1, nullable=False)
    aggregate_type: str = Field(sa_column=Column(String(80), nullable=False))
    aggregate_id: str = Field(sa_column=Column(String(128), nullable=False))
    aggregate_version: Optional[int] = Field(default=None, nullable=True)
    deduplication_key: str = Field(sa_column=Column(String(255), nullable=False))
    idempotency_key: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )
    actor_id: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))
    correlation_id: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))
    causation_id: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))
    payload: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    status: str = Field(default="pending", sa_column=Column(String(32), nullable=False))
    priority: int = Field(default=100, nullable=False)
    attempts: int = Field(default=0, nullable=False)
    max_attempts: int = Field(default=8, nullable=False)
    available_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    worker_id: Optional[str] = Field(default=None, sa_column=Column(String(128), nullable=True))
    lease_token: Optional[str] = Field(default=None, sa_column=Column(String(255), nullable=True))
    lease_expires_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    last_error_code: Optional[str] = Field(default=None, sa_column=Column(String(100), nullable=True))
    last_error_message: Optional[str] = Field(default=None, sa_column=Column(String(1000), nullable=True))
    occurred_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    published_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class ConsumerInbox(SQLModel, table=True):
    __tablename__ = "consumer_inbox"
    __table_args__ = (
        CheckConstraint("handler_version > 0", name="ck_consumer_inbox_handler_version_positive"),
        Index("ix_consumer_inbox_processed_at", "processed_at"),
    )

    consumer_name: str = Field(
        sa_column=Column(String(120), primary_key=True),
    )
    event_id: str = Field(
        sa_column=Column(String(32), primary_key=True),
    )
    handler_version: int = Field(default=1, nullable=False)
    received_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    processed_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
