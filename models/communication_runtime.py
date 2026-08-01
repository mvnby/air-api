from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CommunicationWebsiteCanaryRun(SQLModel, table=True):
    """Immutable target plus durable terminal outcome for one website canary."""

    __tablename__ = "communication_website_canary_run"
    __table_args__ = (
        UniqueConstraint(
            "event_id",
            name="uq_communication_website_canary_run_event_id",
        ),
        CheckConstraint(
            "length(run_id) = 36",
            name="ck_communication_website_canary_run_id_valid",
        ),
        CheckConstraint(
            "length(event_id) = 32",
            name="ck_communication_website_canary_event_id_valid",
        ),
        CheckConstraint(
            "event_type IN ("
            "'crm.installation_estimate_lead.created', "
            "'tenant.website.checkout.created', "
            "'tenant.website.contact_lead.created', "
            "'tenant.website.product_availability.requested', "
            "'tenant.website.repair_diagnostic.created')",
            name="ck_communication_website_canary_event_type_valid",
        ),
        CheckConstraint(
            "tenant_id > 0 AND storefront_id > 0",
            name="ck_communication_website_canary_scope_positive",
        ),
        CheckConstraint(
            "length(trim(recipient_key)) > 0",
            name="ck_communication_website_canary_recipient_valid",
        ),
        CheckConstraint(
            "armed_control_revision > 0",
            name="ck_communication_website_canary_armed_revision_positive",
        ),
        CheckConstraint(
            "(state = 'armed' AND terminal_outcome IS NULL "
            "AND terminal_control_revision IS NULL AND finished_at IS NULL) "
            "OR (state = 'terminal' AND terminal_outcome IN ("
            "'sent', 'dead', 'canceled', 'ambiguous', 'aborted') "
            "AND terminal_control_revision > armed_control_revision "
            "AND finished_at IS NOT NULL)",
            name="ck_communication_website_canary_lifecycle_valid",
        ),
        Index(
            "ix_communication_website_canary_run_state_created",
            "state",
            "created_at",
        ),
    )

    run_id: str = Field(sa_column=Column(String(36), primary_key=True))
    event_id: str = Field(
        sa_column=Column(
            String(32),
            ForeignKey("integration_outbox_event.event_id", ondelete="RESTRICT"),
            nullable=False,
        )
    )
    event_type: str = Field(sa_column=Column(String(120), nullable=False))
    tenant_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    storefront_id: int = Field(sa_column=Column(BigInteger, nullable=False))
    recipient_key: str = Field(sa_column=Column(String(160), nullable=False))
    armed_control_revision: int = Field(
        sa_column=Column(BigInteger, nullable=False)
    )
    state: str = Field(default="armed", sa_column=Column(String(16), nullable=False))
    terminal_outcome: Optional[str] = Field(
        default=None,
        sa_column=Column(String(16), nullable=True),
    )
    terminal_control_revision: Optional[int] = Field(
        default=None,
        sa_column=Column(BigInteger, nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    finished_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )


class CommunicationRuntimeState(SQLModel, table=True):
    """Durable control and liveness state for one communication channel.

    ``mode`` is operator-owned control. Runtime heartbeats update only lifecycle
    fields, so a worker cannot accidentally enable itself while reporting state.
    """

    __tablename__ = "communication_runtime_state"
    __table_args__ = (
        CheckConstraint(
            "length(trim(channel)) > 0",
            name="ck_communication_runtime_channel_nonempty",
        ),
        CheckConstraint(
            "mode IN ('off', 'canary', 'all')",
            name="ck_communication_runtime_mode_valid",
        ),
        CheckConstraint(
            "(mode = 'canary' AND canary_run_id IS NOT NULL "
            "AND length(canary_run_id) = 36) OR "
            "(mode IN ('off', 'all') AND canary_run_id IS NULL)",
            name="ck_communication_runtime_canary_scope_valid",
        ),
        CheckConstraint(
            "control_revision >= 0",
            name="ck_communication_runtime_control_revision_non_negative",
        ),
        CheckConstraint(
            "canary_kind IN ('operations', 'website')",
            name="ck_communication_runtime_canary_kind_valid",
        ),
        CheckConstraint(
            "(canary_kind = 'operations' AND website_canary_run_id IS NULL) "
            "OR (canary_kind = 'website' AND mode = 'canary' "
            "AND website_canary_run_id IS NOT NULL "
            "AND website_canary_run_id = canary_run_id)",
            name="ck_communication_runtime_canary_reference_valid",
        ),
        CheckConstraint(
            "mode <> 'all' OR installation_estimate_watermark_at IS NOT NULL",
            name="ck_communication_runtime_all_watermark_required",
        ),
        CheckConstraint(
            "status IN ('stopped', 'fencing', 'disabled', 'paused', "
            "'running', 'stopping', 'faulted')",
            name="ck_communication_runtime_status_valid",
        ),
        Index(
            "ix_communication_runtime_state_heartbeat_at",
            "heartbeat_at",
        ),
    )

    channel: str = Field(sa_column=Column(String(32), primary_key=True))
    mode: str = Field(
        default="off",
        sa_column=Column(String(16), nullable=False),
    )
    canary_run_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(36), nullable=True),
    )
    canary_kind: str = Field(
        default="operations",
        sa_column=Column(
            String(16),
            nullable=False,
            server_default=text("'operations'"),
        ),
    )
    website_canary_run_id: Optional[str] = Field(
        default=None,
        sa_column=Column(
            String(36),
            ForeignKey("communication_website_canary_run.run_id"),
            nullable=True,
        ),
    )
    control_revision: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
    )
    installation_estimate_watermark_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    status: str = Field(
        default="stopped",
        sa_column=Column(String(32), nullable=False),
    )
    instance_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(128), nullable=True),
    )
    started_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    heartbeat_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_activity_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_error_code: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100), nullable=True),
    )
    control_updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
