"""Append-only private evidence files belonging to an order document."""

from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Column, DateTime, ForeignKeyConstraint, String
from sqlmodel import Field, SQLModel


class OrderDocumentExternalFile(SQLModel, table=True):
    __tablename__ = "order_document_external_file"
    __table_args__ = (
        ForeignKeyConstraint(
            ["document_id", "tenant_id"],
            ["order_document.id", "order_document.tenant_id"],
            name="fk_external_file_document_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint("role IN ('original', 'signed_copy')", name="ck_external_file_role"),
        CheckConstraint("version > 0", name="ck_external_file_version"),
        CheckConstraint("size_bytes > 0", name="ck_external_file_size"),
        CheckConstraint("length(checksum_sha256) = 64", name="ck_external_file_sha256"),
    )

    document_id: int = Field(primary_key=True)
    version: int = Field(primary_key=True)
    tenant_id: int = Field(nullable=False)
    role: str = Field(sa_column=Column(String(16), nullable=False))
    filename: str = Field(sa_column=Column(String(255), nullable=False))
    mime_type: str = Field(sa_column=Column(String(160), nullable=False))
    size_bytes: int = Field(nullable=False)
    checksum_sha256: str = Field(sa_column=Column(String(64), nullable=False))
    provider: str = Field(sa_column=Column(String(40), nullable=False))
    storage_key: str = Field(sa_column=Column(String(1000), nullable=False))
    uploaded_by_staff_user_id: int = Field(nullable=False)
    uploaded_by: str = Field(sa_column=Column(String(255), nullable=False))
    uploaded_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc),
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
