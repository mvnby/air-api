from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, Column, DateTime, Index, Integer, String
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuthLoginThrottle(SQLModel, table=True):
    """Cross-node failed-login counter without raw account identifiers."""

    __tablename__ = "auth_login_throttle"
    __table_args__ = (
        CheckConstraint(
            "length(fingerprint) = 64",
            name="ck_auth_login_throttle_fingerprint_length",
        ),
        CheckConstraint(
            "failure_count >= 0",
            name="ck_auth_login_throttle_failure_count_nonnegative",
        ),
        Index("ix_auth_login_throttle_updated_at", "updated_at"),
    )

    fingerprint: str = Field(sa_column=Column(String(64), primary_key=True))
    failure_count: int = Field(
        default=0,
        sa_column=Column(Integer, nullable=False, server_default="0"),
    )
    window_started_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    blocked_until: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
