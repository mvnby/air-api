"""Durable HA coordination for bounded storage maintenance."""

from datetime import datetime, timezone

from sqlalchemy import Column, DateTime, String
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class StorageReconciliationCursor(SQLModel, table=True):
    __tablename__ = "storage_reconciliation_cursor"

    name: str = Field(
        sa_column=Column(String(160), primary_key=True, nullable=False),
    )
    storage_provider: str = Field(sa_column=Column(String(32), nullable=False))
    cursor: str | None = Field(
        default=None,
        sa_column=Column(String(1024), nullable=True),
    )
    lease_owner: str | None = Field(
        default=None,
        sa_column=Column(String(128), nullable=True),
    )
    lease_token: str | None = Field(
        default=None,
        sa_column=Column(String(64), nullable=True),
    )
    lease_expires_at: datetime | None = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    updated_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
