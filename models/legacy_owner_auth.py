from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKey, Integer, String
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LegacyOwnerAuthState(SQLModel, table=True):
    """Singleton cutover fence for the runtime-env system owner."""

    __tablename__ = "legacy_owner_auth_state"
    __table_args__ = (
        CheckConstraint("id = 1", name="ck_legacy_owner_auth_state_singleton"),
        CheckConstraint(
            "mode IN ('legacy', 'staff_shadow', 'staff')",
            name="ck_legacy_owner_auth_state_mode_valid",
        ),
        CheckConstraint(
            "legacy_token_version >= 1",
            name="ck_legacy_owner_auth_state_token_version_positive",
        ),
        CheckConstraint(
            "mode = 'legacy' OR owner_staff_user_id IS NOT NULL",
            name="ck_legacy_owner_auth_state_staff_mode_bound",
        ),
    )

    id: int = Field(
        default=1,
        sa_column=Column(Integer, primary_key=True, nullable=False),
    )
    mode: str = Field(
        default="legacy",
        sa_column=Column(String(24), nullable=False, server_default="legacy"),
    )
    legacy_token_version: int = Field(
        default=1,
        sa_column=Column(Integer, nullable=False, server_default="1"),
    )
    owner_staff_user_id: Optional[int] = Field(
        default=None,
        sa_column=Column(
            Integer,
            ForeignKey("staff_users.id", ondelete="RESTRICT"),
            nullable=True,
            unique=True,
        ),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


__all__ = ["LegacyOwnerAuthState"]
