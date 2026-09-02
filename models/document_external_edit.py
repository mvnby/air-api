from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from uuid import uuid4

from sqlalchemy import CheckConstraint, Column, DateTime, Index, String
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentExternalEditSession(SQLModel, table=True):
    """Tenant-owned link between an immutable CRM source and an online editor.

    The subject shape is intentionally provider-neutral so generated document
    artifacts can use the same audited round-trip without weakening template
    version immutability.
    """

    __tablename__ = "document_external_edit_session"
    __table_args__ = (
        CheckConstraint(
            "subject_type IN ('template_version', 'document_artifact')",
            name="ck_document_external_edit_subject_type_valid",
        ),
        CheckConstraint(
            "(subject_type = 'template_version' "
            "AND template_version_id IS NOT NULL "
            "AND document_artifact_id IS NULL) OR "
            "(subject_type = 'document_artifact' "
            "AND document_artifact_id IS NOT NULL "
            "AND template_version_id IS NULL)",
            name="ck_document_external_edit_exactly_one_subject",
        ),
        CheckConstraint(
            "status IN ('ready', 'changed', 'syncing', 'error')",
            name="ck_document_external_edit_status_valid",
        ),
        CheckConstraint(
            "length(trim(provider)) > 0",
            name="ck_document_external_edit_provider_nonempty",
        ),
        CheckConstraint(
            "length(trim(provider_connection_id)) > 0",
            name="ck_document_external_edit_connection_nonempty",
        ),
        CheckConstraint(
            "length(base_checksum_sha256) = 64",
            name="ck_document_external_edit_checksum_length",
        ),
        CheckConstraint(
            "active_sync_fingerprint IS NULL OR length(active_sync_fingerprint) = 64",
            name="ck_document_external_edit_active_fingerprint_length",
        ),
        CheckConstraint(
            "last_sync_fingerprint IS NULL OR length(last_sync_fingerprint) = 64",
            name="ck_document_external_edit_last_fingerprint_length",
        ),
        Index(
            "uq_document_external_edit_template_provider",
            "tenant_id",
            "provider",
            "provider_connection_id",
            "template_version_id",
            unique=True,
        ),
        Index(
            "uq_document_external_edit_artifact_provider",
            "tenant_id",
            "provider",
            "provider_connection_id",
            "document_artifact_id",
            unique=True,
        ),
    )

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        sa_column=Column(String(32), primary_key=True),
    )
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    subject_type: str = Field(sa_column=Column(String(32), nullable=False, index=True))
    template_version_id: Optional[int] = Field(
        default=None,
        foreign_key="document_template_version.id",
        ondelete="RESTRICT",
        nullable=True,
        index=True,
    )
    document_artifact_id: Optional[str] = Field(
        default=None,
        foreign_key="document_artifact.id",
        ondelete="RESTRICT",
        sa_type=String(32),
        nullable=True,
        index=True,
    )
    provider: str = Field(sa_column=Column(String(40), nullable=False))
    provider_connection_id: str = Field(sa_column=Column(String(160), nullable=False))
    remote_file_id: Optional[str] = Field(
        default=None, sa_column=Column(String(500), nullable=True)
    )
    edit_url: Optional[str] = Field(
        default=None, sa_column=Column(String(2000), nullable=True)
    )
    remote_filename: Optional[str] = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    remote_mime_type: Optional[str] = Field(
        default=None, sa_column=Column(String(160), nullable=True)
    )
    base_checksum_sha256: str = Field(sa_column=Column(String(64), nullable=False))
    remote_revision: Optional[str] = Field(
        default=None, sa_column=Column(String(500), nullable=True)
    )
    status: str = Field(
        default="syncing",
        sa_column=Column(String(24), nullable=False, index=True),
    )
    detail: Optional[str] = Field(
        default=None, sa_column=Column(String(1000), nullable=True)
    )
    active_sync_key: Optional[str] = Field(
        default=None, sa_column=Column(String(160), nullable=True)
    )
    active_sync_fingerprint: Optional[str] = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    last_sync_key: Optional[str] = Field(
        default=None, sa_column=Column(String(160), nullable=True)
    )
    last_sync_fingerprint: Optional[str] = Field(
        default=None, sa_column=Column(String(64), nullable=True)
    )
    last_sync_remote_revision: Optional[str] = Field(
        default=None, sa_column=Column(String(500), nullable=True)
    )
    last_imported_template_version_id: Optional[int] = Field(
        default=None,
        foreign_key="document_template_version.id",
        ondelete="RESTRICT",
        nullable=True,
    )
    created_by_staff_user_id: Optional[int] = Field(
        default=None,
        foreign_key="staff_users.id",
        ondelete="SET NULL",
        nullable=True,
        index=True,
    )
    last_synced_by_staff_user_id: Optional[int] = Field(
        default=None,
        foreign_key="staff_users.id",
        ondelete="SET NULL",
        nullable=True,
        index=True,
    )
    remote_modified_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    last_synced_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
