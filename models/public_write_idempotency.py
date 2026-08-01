from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, Index, JSON, String, UniqueConstraint
from sqlmodel import Field, SQLModel


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class PublicWriteIdempotency(SQLModel, table=True):
    """Durable receipt for one public storefront command.

    The client key and request content are represented only by SHA-256 digests.
    Response bodies are restricted by the service before they reach this table.
    """

    __tablename__ = "public_write_idempotency"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "storefront_id",
            "command_name",
            "key_hash",
            name="uq_public_write_idempotency_scope_command_key",
        ),
        Index(
            "ix_public_write_idempotency_scope_created_at",
            "tenant_id",
            "storefront_id",
            "created_at",
        ),
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"],
            ["storefront.id", "storefront.tenant_id"],
            name="fk_public_write_idempotency_storefront_tenant",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)
    storefront_id: int = Field(nullable=False)
    command_name: str = Field(sa_column=Column(String(80), nullable=False))
    key_hash: str = Field(sa_column=Column(String(64), nullable=False))
    request_fingerprint: str = Field(sa_column=Column(String(64), nullable=False))
    response_status: Optional[int] = Field(default=None, nullable=True)
    response_body: Optional[dict[str, Any]] = Field(
        default=None,
        sa_column=Column(JSON, nullable=True),
    )
    resource_type: Optional[str] = Field(
        default=None,
        sa_column=Column(String(40), nullable=True),
    )
    resource_id: Optional[int] = Field(default=None, nullable=True)
    created_at: datetime = Field(
        default_factory=_utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    completed_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
