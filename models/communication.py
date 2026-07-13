from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, JSON, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CommunicationDelivery(SQLModel, table=True):
    __tablename__ = "communication_delivery"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            "channel",
            "recipient_key",
            "template_version",
            name="uq_communication_delivery_event_channel_recipient_template",
        ),
        CheckConstraint("template_version > 0", name="ck_delivery_template_version_positive"),
        CheckConstraint("attempts >= 0", name="ck_delivery_attempts_non_negative"),
        CheckConstraint("max_attempts > 0", name="ck_delivery_max_attempts_positive"),
        CheckConstraint(
            "attempts <= max_attempts",
            name="ck_delivery_attempts_within_max",
        ),
        CheckConstraint(
            "status NOT IN ('queued', 'retry') OR attempts < max_attempts",
            name="ck_delivery_active_attempts_remaining",
        ),
        CheckConstraint(
            "status IN ('queued', 'running', 'retry', 'sent', 'dead', 'canceled')",
            name="ck_delivery_status_valid",
        ),
        CheckConstraint(
            "(status = 'running' AND worker_id IS NOT NULL "
            "AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL) "
            "OR (status <> 'running' AND worker_id IS NULL "
            "AND lease_token IS NULL AND lease_expires_at IS NULL)",
            name="ck_delivery_lease_state",
        ),
        CheckConstraint(
            "(status = 'sent' AND sent_at IS NOT NULL AND finished_at IS NOT NULL) "
            "OR (status IN ('dead', 'canceled') AND sent_at IS NULL "
            "AND finished_at IS NOT NULL) "
            "OR (status IN ('queued', 'running', 'retry') AND sent_at IS NULL "
            "AND finished_at IS NULL)",
            name="ck_delivery_terminal_timestamps",
        ),
        CheckConstraint(
            "(status = 'queued' AND attempts = 0) "
            "OR (status IN ('running', 'retry', 'sent', 'dead', 'canceled') "
            "AND attempts >= 1)",
            name="ck_delivery_attempt_phase",
        ),
        CheckConstraint(
            "(status = 'sent' AND provider_message_id IS NOT NULL "
            "AND length(trim(provider_message_id)) > 0) "
            "OR (status <> 'sent' AND provider_message_id IS NULL)",
            name="ck_delivery_provider_message_state",
        ),
        Index(
            "ix_communication_delivery_claim",
            "status",
            "available_at",
            "priority",
            "created_at",
        ),
        Index(
            "ix_communication_delivery_channel_claim",
            "channel",
            "priority",
            "available_at",
            "created_at",
            "delivery_id",
            postgresql_where=text("status IN ('queued', 'retry')"),
        ),
        Index(
            "ix_communication_delivery_channel_recovery",
            "channel",
            "lease_expires_at",
            "created_at",
            "delivery_id",
            postgresql_where=text("status = 'running'"),
        ),
        Index("ix_communication_delivery_event_id", "event_id"),
    )

    delivery_id: str = Field(
        sa_column=Column(String(32), primary_key=True),
    )
    event_id: str = Field(sa_column=Column(String(32), nullable=False))
    channel: str = Field(sa_column=Column(String(32), nullable=False))
    recipient_key: str = Field(sa_column=Column(String(160), nullable=False))
    destination: str = Field(sa_column=Column(String(255), nullable=False))
    template_key: str = Field(sa_column=Column(String(120), nullable=False))
    template_version: int = Field(default=1, nullable=False)
    render_context: dict[str, Any] = Field(
        default_factory=dict,
        sa_column=Column(JSON, nullable=False),
    )
    status: str = Field(default="queued", sa_column=Column(String(32), nullable=False))
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
    provider_message_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(255), nullable=True),
    )
    last_error_category: Optional[str] = Field(
        default=None,
        sa_column=Column(String(80), nullable=True),
    )
    last_error_code: Optional[str] = Field(default=None, sa_column=Column(String(100), nullable=True))
    last_error_message: Optional[str] = Field(default=None, sa_column=Column(String(1000), nullable=True))
    sent_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True),
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
