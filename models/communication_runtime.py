from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import BigInteger, CheckConstraint, Column, DateTime, Index, String
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


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
    control_revision: int = Field(
        default=0,
        sa_column=Column(BigInteger, nullable=False),
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
