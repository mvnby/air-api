from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
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


class CommunicationDeliveryAttempt(SQLModel, table=True):
    """PII-free lifecycle journal for one provider delivery attempt."""

    __tablename__ = "communication_delivery_attempt"
    __table_args__ = (
        CheckConstraint("attempt_no > 0", name="ck_delivery_attempt_no_positive"),
        CheckConstraint(
            "outcome IN ('running', 'sent', 'retry', 'dead', 'canceled')",
            name="ck_delivery_attempt_outcome_valid",
        ),
        CheckConstraint(
            "(outcome = 'running' AND finished_at IS NULL) "
            "OR (outcome <> 'running' AND finished_at IS NOT NULL)",
            name="ck_delivery_attempt_finish_state",
        ),
        CheckConstraint(
            "finished_at IS NULL OR finished_at >= started_at",
            name="ck_delivery_attempt_finished_after_started",
        ),
        CheckConstraint(
            "(outcome IN ('running', 'sent') AND error_category IS NULL "
            "AND error_code IS NULL) OR "
            "(outcome IN ('retry', 'dead', 'canceled') "
            "AND error_category IS NOT NULL AND length(trim(error_category)) > 0 "
            "AND error_code IS NOT NULL AND length(trim(error_code)) > 0)",
            name="ck_delivery_attempt_error_state",
        ),
        CheckConstraint(
            "retry_after_seconds IS NULL OR retry_after_seconds > 0",
            name="ck_delivery_attempt_retry_after_positive",
        ),
        CheckConstraint(
            "retry_after_seconds IS NULL OR outcome IN ('retry', 'dead')",
            name="ck_delivery_attempt_retry_after_state",
        ),
        CheckConstraint(
            "provider_latency_ms IS NULL OR provider_latency_ms >= 0",
            name="ck_delivery_attempt_latency_non_negative",
        ),
        CheckConstraint(
            "provider_latency_ms IS NULL OR outcome IN ('sent', 'retry', 'dead')",
            name="ck_delivery_attempt_latency_state",
        ),
        CheckConstraint(
            "ambiguous = false OR outcome IN ('retry', 'dead')",
            name="ck_delivery_attempt_ambiguity_state",
        ),
        Index(
            "ix_delivery_attempt_outcome_started",
            "outcome",
            "started_at",
        ),
        Index(
            "ix_delivery_attempt_error_finished",
            "error_category",
            "error_code",
            "finished_at",
        ),
        Index(
            "ix_delivery_attempt_ambiguous_finished",
            "finished_at",
            postgresql_where=text("ambiguous = true"),
            sqlite_where=text("ambiguous = 1"),
        ),
    )

    delivery_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("communication_delivery.delivery_id"),
            primary_key=True,
        ),
    )
    attempt_no: int = Field(primary_key=True)
    started_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    outcome: str = Field(sa_column=Column(String(32), nullable=False))
    error_category: Optional[str] = Field(
        default=None,
        sa_column=Column(String(80), nullable=True),
    )
    error_code: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100), nullable=True),
    )
    retry_after_seconds: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    provider_latency_ms: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    ambiguous: bool = Field(
        default=False,
        sa_column=Column(
            Boolean,
            nullable=False,
            server_default=text("false"),
        ),
    )
