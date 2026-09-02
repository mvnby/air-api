from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlmodel import Field, SQLModel

from models.tenancy import utc_now


class DocumentDriveConnection(SQLModel, table=True):
    """Encrypted Google Drive credentials owned by one tenant."""

    __tablename__ = "document_drive_connection"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "provider",
            name="uq_document_drive_connection_tenant_provider",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_document_drive_connection_status_valid",
        ),
        Index("ix_document_drive_connection_tenant", "tenant_id"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(
        foreign_key="tenant.id",
        ondelete="CASCADE",
        nullable=False,
    )
    provider: str = Field(
        default="google_drive",
        sa_column=Column(String(48), nullable=False),
    )
    status: str = Field(
        default="active",
        sa_column=Column(String(24), nullable=False),
    )
    encrypted_credentials: str = Field(sa_column=Column(Text, nullable=False))
    credentials_fingerprint: str = Field(
        sa_column=Column(String(64), nullable=False),
    )
    connection_key: str = Field(
        sa_column=Column(String(64), nullable=False),
    )
    account_label: Optional[str] = Field(
        default=None,
        sa_column=Column(String(320), nullable=True),
    )
    managed_folder_id: Optional[str] = Field(
        default=None,
        sa_column=Column(String(160), nullable=True),
    )
    managed_folder_url: Optional[str] = Field(
        default=None,
        sa_column=Column(String(1024), nullable=True),
    )
    connected_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    last_verified_at: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True),
    )
    last_error_code: Optional[str] = Field(
        default=None,
        sa_column=Column(String(80), nullable=True),
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
