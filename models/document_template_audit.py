"""Tenant-owned review evidence; native template versions remain authoritative."""

from datetime import datetime
from typing import Any

from sqlalchemy import Column, DateTime, JSON, String, UniqueConstraint
from sqlmodel import Field, SQLModel

from models.document import utc_now


class DocumentTemplateAudit(SQLModel, table=True):
    __tablename__ = "document_template_audit"
    __table_args__ = (
        UniqueConstraint(
            "tenant_id",
            "template_id",
            "version_id",
            "context_hash",
            name="uq_template_audit_context",
        ),
    )

    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    legal_entity_id: int = Field(foreign_key="document_legal_entity.id", index=True)
    template_id: int = Field(foreign_key="document_template.id", index=True)
    version_id: int = Field(foreign_key="document_template_version.id", index=True)
    customer_id: int | None = Field(default=None, foreign_key="customer.id")
    source_hash: str = Field(sa_column=Column(String(64), nullable=False))
    context_hash: str = Field(sa_column=Column(String(64), nullable=False))
    legal_sources_hash: str = Field(sa_column=Column(String(64), nullable=False))
    revision: int = Field(default=1)
    checked_at: datetime = Field(
        sa_column=Column(DateTime(timezone=True), nullable=False)
    )
    review_date: str
    coverage: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    checklist: dict[str, Any] = Field(sa_column=Column(JSON, nullable=False))
    findings: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    history: list[dict[str, Any]] = Field(
        default_factory=list, sa_column=Column(JSON, nullable=False)
    )
    created_by: int = Field(foreign_key="staff_users.id")
    channel: str
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )


class DocumentTemplateAuditProposal(SQLModel, table=True):
    __tablename__ = "document_template_audit_proposal"
    id: int | None = Field(default=None, primary_key=True)
    tenant_id: int = Field(foreign_key="tenant.id", index=True)
    report_id: int = Field(foreign_key="document_template_audit.id", index=True)
    base_version_id: int = Field(foreign_key="document_template_version.id")
    version_id: int = Field(foreign_key="document_template_version.id", unique=True)
    source_hash: str = Field(sa_column=Column(String(64), nullable=False))
    context_hash: str = Field(sa_column=Column(String(64), nullable=False))
    legal_sources_hash: str = Field(sa_column=Column(String(64), nullable=False))
    edits: list[dict[str, Any]] = Field(sa_column=Column(JSON, nullable=False))
    created_by: int = Field(foreign_key="staff_users.id")
    channel: str
    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), nullable=False),
    )
