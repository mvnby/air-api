"""Immutable, tenant-owned registration certificate versions."""

from datetime import datetime
from uuid import uuid4
from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    String,
    text,
    CheckConstraint,
)
from sqlmodel import SQLModel, Field
from models.document import utc_now


class LegalEntityAttachment(SQLModel, table=True):
    __tablename__ = "legal_entity_attachment"
    __table_args__ = (
        ForeignKeyConstraint(
            ["legal_entity_id", "tenant_id"],
            ["document_legal_entity.id", "document_legal_entity.tenant_id"],
            ondelete="RESTRICT",
        ),
        CheckConstraint("size_bytes > 0 AND size_bytes <= 10485760"),
        CheckConstraint("mime_type IN ('application/pdf', 'image/jpeg', 'image/png')"),
        Index(
            "uq_legal_entity_attachment_current",
            "tenant_id",
            "legal_entity_id",
            unique=True,
            postgresql_where=text("is_current"),
            sqlite_where=text("is_current = 1"),
        ),
    )
    id: str = Field(
        default_factory=lambda: uuid4().hex,
        sa_column=Column(String(32), primary_key=True),
    )
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    legal_entity_id: int = Field(nullable=False, index=True)
    filename: str = Field(max_length=200)
    mime_type: str = Field(max_length=40)
    provider: str = Field(max_length=40)
    storage_key: str = Field(max_length=1000)
    checksum_sha256: str = Field(max_length=64)
    size_bytes: int
    is_current: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
