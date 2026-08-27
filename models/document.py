from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    ForeignKeyConstraint,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
    text,
)
from sqlmodel import Field, SQLModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class DocumentLegalEntity(SQLModel, table=True):
    """Tenant-owned issuer whose official numbering and templates are isolated."""

    __tablename__ = "document_legal_entity"
    __table_args__ = (
        UniqueConstraint("id", "tenant_id", name="uq_document_legal_entity_id_tenant"),
        UniqueConstraint(
            "tenant_id", "slug", name="uq_document_legal_entity_tenant_slug"
        ),
        Index(
            "uq_document_legal_entity_default_per_tenant",
            "tenant_id",
            unique=True,
            postgresql_where=text("is_default"),
            sqlite_where=text("is_default = 1"),
        ),
        CheckConstraint(
            "length(trim(slug)) > 0", name="ck_document_legal_entity_slug_nonempty"
        ),
        CheckConstraint(
            "length(trim(display_name)) > 0",
            name="ck_document_legal_entity_name_nonempty",
        ),
        CheckConstraint(
            "status IN ('active', 'disabled')",
            name="ck_document_legal_entity_status_valid",
        ),
        CheckConstraint(
            "entity_type IN ('organization', 'individual_entrepreneur')",
            name="ck_document_legal_entity_type_valid",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    slug: str = Field(sa_column=Column(String(80), nullable=False))
    display_name: str = Field(sa_column=Column(String(200), nullable=False))
    legal_name: Optional[str] = Field(
        default=None, sa_column=Column(String(500), nullable=True)
    )
    unp: Optional[str] = Field(
        default=None, sa_column=Column(String(32), nullable=True)
    )
    entity_type: str = Field(
        default="organization",
        sa_column=Column(
            String(32), nullable=False, server_default="organization", index=True
        ),
    )
    is_vat_payer: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    is_default: bool = Field(default=False, sa_column=Column(Boolean, nullable=False))
    requisites: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    status: str = Field(
        default="active", sa_column=Column(String(24), nullable=False, index=True)
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class DocumentArtifact(SQLModel, table=True):
    """Immutable stored bytes produced from a document/template snapshot."""

    __tablename__ = "document_artifact"
    __table_args__ = (
        ForeignKeyConstraint(
            ["order_document_id", "tenant_id"],
            ["order_document.id", "order_document.tenant_id"],
            name="fk_document_artifact_order_document_tenant",
            ondelete="RESTRICT",
        ),
        CheckConstraint(
            "kind IN ('source_docx', 'rendered_docx', 'pdf')",
            name="ck_document_artifact_kind_valid",
        ),
        CheckConstraint(
            "length(trim(provider)) > 0", name="ck_document_artifact_provider_nonempty"
        ),
        CheckConstraint(
            "length(trim(storage_key)) > 0",
            name="ck_document_artifact_storage_key_nonempty",
        ),
        CheckConstraint(
            "size_bytes >= 0", name="ck_document_artifact_size_non_negative"
        ),
        Index(
            "uq_document_artifact_authoritative_kind",
            "order_document_id",
            "kind",
            unique=True,
            postgresql_where=text("is_authoritative"),
            sqlite_where=text("is_authoritative = 1"),
        ),
    )

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        sa_column=Column(String(32), primary_key=True),
    )
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    order_document_id: int = Field(
        sa_column=Column(Integer, nullable=False, index=True)
    )
    kind: str = Field(sa_column=Column(String(32), nullable=False, index=True))
    provider: str = Field(sa_column=Column(String(40), nullable=False))
    storage_key: str = Field(sa_column=Column(String(1000), nullable=False))
    content_type: str = Field(sa_column=Column(String(160), nullable=False))
    filename: str = Field(sa_column=Column(String(255), nullable=False))
    checksum_sha256: str = Field(sa_column=Column(String(64), nullable=False))
    size_bytes: int = Field(nullable=False)
    is_authoritative: bool = Field(
        default=False, sa_column=Column(Boolean, nullable=False)
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class DocumentTemplateVersion(SQLModel, table=True):
    """Immutable template source revision; activation is lifecycle metadata."""

    __tablename__ = "document_template_version"
    __table_args__ = (
        UniqueConstraint(
            "template_id", "version", name="uq_document_template_version_number"
        ),
        CheckConstraint("version > 0", name="ck_document_template_version_positive"),
        CheckConstraint(
            "status IN ('draft', 'active', 'retired')",
            name="ck_document_template_version_status_valid",
        ),
        CheckConstraint(
            "renderer IN ('docx', 'google_docs', 'google_sheets')",
            name="ck_document_template_version_renderer_valid",
        ),
        Index(
            "uq_document_template_version_active",
            "template_id",
            unique=True,
            postgresql_where=text("status = 'active'"),
            sqlite_where=text("status = 'active'"),
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    template_id: int = Field(
        foreign_key="document_template.id",
        ondelete="CASCADE",
        nullable=False,
        index=True,
    )
    version: int = Field(nullable=False)
    status: str = Field(
        default="draft", sa_column=Column(String(24), nullable=False, index=True)
    )
    renderer: str = Field(sa_column=Column(String(32), nullable=False))
    source_storage_key: str = Field(sa_column=Column(String(500), nullable=False))
    source_filename: Optional[str] = Field(
        default=None, sa_column=Column(String(255), nullable=True)
    )
    checksum_sha256: str = Field(sa_column=Column(String(64), nullable=False))
    placeholder_schema: dict[str, Any] = Field(
        default_factory=dict, sa_column=Column(JSON, nullable=False)
    )
    change_note: Optional[str] = Field(
        default=None, sa_column=Column(String(1000), nullable=True)
    )
    activated_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class DocumentNumberSequence(SQLModel, table=True):
    """Atomic counter for one tenant/legal-entity/type/series/period scope."""

    __tablename__ = "document_number_sequence"
    __table_args__ = (
        ForeignKeyConstraint(
            ["legal_entity_id", "tenant_id"],
            ["document_legal_entity.id", "document_legal_entity.tenant_id"],
            name="fk_document_number_sequence_legal_entity_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "legal_entity_id",
            "document_type",
            "series",
            "period_key",
            name="uq_document_number_sequence_scope",
        ),
        CheckConstraint(
            "last_value >= 0", name="ck_document_number_sequence_non_negative"
        ),
        CheckConstraint(
            "length(trim(document_type)) > 0",
            name="ck_document_number_sequence_type_nonempty",
        ),
        CheckConstraint(
            "length(trim(period_key)) > 0",
            name="ck_document_number_sequence_period_nonempty",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    legal_entity_id: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    document_type: str = Field(sa_column=Column(String(64), nullable=False))
    series: str = Field(default="", sa_column=Column(String(64), nullable=False))
    period_key: str = Field(sa_column=Column(String(32), nullable=False))
    last_value: int = Field(default=0, nullable=False)
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class DocumentNumberPolicy(SQLModel, table=True):
    """Tenant-configurable official numbering policy for one issuer/type."""

    __tablename__ = "document_number_policy"
    __table_args__ = (
        ForeignKeyConstraint(
            ["legal_entity_id", "tenant_id"],
            ["document_legal_entity.id", "document_legal_entity.tenant_id"],
            name="fk_document_number_policy_legal_entity_tenant",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "legal_entity_id",
            "document_type",
            name="uq_document_number_policy_scope",
        ),
        CheckConstraint(
            "period_mode IN ('calendar_year', 'continuous', 'per_basis')",
            name="ck_document_number_policy_period_mode_valid",
        ),
        CheckConstraint(
            "minimum_width >= 1 AND minimum_width <= 12",
            name="ck_document_number_policy_width_valid",
        ),
        CheckConstraint(
            "length(trim(document_type)) > 0",
            name="ck_document_number_policy_type_nonempty",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    legal_entity_id: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    document_type: str = Field(sa_column=Column(String(64), nullable=False, index=True))
    series: str = Field(default="", sa_column=Column(String(64), nullable=False))
    period_mode: str = Field(
        default="calendar_year", sa_column=Column(String(32), nullable=False)
    )
    minimum_width: int = Field(default=3, nullable=False)
    is_active: bool = Field(default=True, sa_column=Column(Boolean, nullable=False))
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class DocumentNumberReservation(SQLModel, table=True):
    """Durable, idempotent allocation. Rows are retained after void/replacement."""

    __tablename__ = "document_number_reservation"
    __table_args__ = (
        ForeignKeyConstraint(
            ["legal_entity_id", "tenant_id"],
            ["document_legal_entity.id", "document_legal_entity.tenant_id"],
            name="fk_document_number_reservation_legal_entity_tenant",
            ondelete="RESTRICT",
        ),
        ForeignKeyConstraint(
            ["document_id", "tenant_id", "legal_entity_id"],
            [
                "order_document.id",
                "order_document.tenant_id",
                "order_document.legal_entity_id",
            ],
            name="fk_document_number_reservation_document_scope",
            ondelete="RESTRICT",
        ),
        UniqueConstraint(
            "tenant_id",
            "legal_entity_id",
            "document_type",
            "series",
            "period_key",
            "number_value",
            name="uq_document_number_reservation_value",
        ),
        UniqueConstraint(
            "tenant_id",
            "idempotency_key",
            name="uq_document_number_reservation_idempotency",
        ),
        Index(
            "uq_document_number_reservation_document",
            "tenant_id",
            "document_id",
            unique=True,
            postgresql_where=text("document_id IS NOT NULL"),
            sqlite_where=text("document_id IS NOT NULL"),
        ),
        CheckConstraint(
            "number_value > 0", name="ck_document_number_reservation_positive"
        ),
        CheckConstraint(
            "status IN ('reserved', 'assigned', 'void')",
            name="ck_document_number_reservation_status_valid",
        ),
    )

    id: str = Field(
        default_factory=lambda: uuid4().hex,
        sa_column=Column(String(32), primary_key=True),
    )
    tenant_id: int = Field(foreign_key="tenant.id", nullable=False, index=True)
    legal_entity_id: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    document_id: Optional[int] = Field(
        default=None, sa_column=Column(Integer, nullable=True, index=True)
    )
    document_type: str = Field(sa_column=Column(String(64), nullable=False))
    series: str = Field(default="", sa_column=Column(String(64), nullable=False))
    period_key: str = Field(sa_column=Column(String(32), nullable=False))
    number_value: int = Field(nullable=False)
    number_text: str = Field(sa_column=Column(String(160), nullable=False))
    idempotency_key: str = Field(sa_column=Column(String(255), nullable=False))
    status: str = Field(
        default="reserved", sa_column=Column(String(24), nullable=False, index=True)
    )
    reserved_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
    assigned_at: Optional[datetime] = Field(
        default=None, sa_column=Column(DateTime(timezone=True), nullable=True)
    )
