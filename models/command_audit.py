"""Committed changes through authenticated application commands."""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import Column, DateTime, ForeignKeyConstraint, Index, String
from sqlmodel import Field, SQLModel


class CommandAuditEvent(SQLModel, table=True):
    __tablename__ = "command_audit_event"
    __table_args__ = (
        ForeignKeyConstraint(
            ["storefront_id", "tenant_id"], ["storefront.id", "storefront.tenant_id"]
        ),
        Index(
            "ix_command_audit_scope_created", "tenant_id", "storefront_id", "created_at"
        ),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False)
    storefront_id: int = Field(nullable=False)
    staff_user_id: int = Field(foreign_key="staff_users.id", nullable=False)
    channel: str = Field(sa_column=Column(String(32), nullable=False))
    operation: str = Field(sa_column=Column(String(80), nullable=False))
    request_id: str = Field(sa_column=Column(String(64), nullable=False))
    resource_type: Optional[str] = Field(default=None, max_length=40)
    resource_id: Optional[int] = None
    result: str = Field(default="committed", max_length=32)
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
