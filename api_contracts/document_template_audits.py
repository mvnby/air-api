"""Shared Manager/MCP template review contracts. Source text is untrusted data."""

from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, HttpUrl

from schemas_connector_mcp import ConnectorInput, WriteInput


class TemplateAuditListInput(ConnectorInput):
    legal_entity_id: int | None = Field(default=None, gt=0)
    document_type: str | None = Field(default=None, max_length=64)
    active: bool | None = True
    customer_id: int | None = Field(default=None, gt=0)
    contract_scenario: str | None = Field(default=None, max_length=32)
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=25, ge=1, le=100)


class TemplateAuditReadInput(ConnectorInput):
    legal_entity_id: int = Field(gt=0)
    template_id: int = Field(gt=0)
    version_id: int | None = Field(default=None, gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    include_archived: bool = False
    include_source_file: bool = False
    versions_page: int = Field(default=1, ge=1)
    audit_reports_page: int = Field(default=1, ge=1)
    cursor: str | None = Field(default=None, max_length=512)
    limit: int = Field(default=20, ge=1, le=50)


class TemplateAuditListResult(BaseModel):
    items: list[dict[str, Any]]
    page: int
    limit: int
    total: int


class TemplateAuditReadResult(BaseModel):
    template: dict[str, Any]
    version: dict[str, Any] | None
    versions: list[dict[str, Any]]
    versions_total: int
    audit_reports: list[dict[str, Any]] = Field(default_factory=list)
    audit_reports_total: int = 0
    audit_reports_next_page: int | None = None
    context: dict[str, Any]
    context_hash: str
    source_hash: str | None
    coverage: dict[str, Any]
    blocks: list[dict[str, Any]]
    next_cursor: str | None
    placeholder_catalog: dict[str, Any]
    content_kind: Literal["template_source"] = "template_source"
    manager_url: str
    source_resource_uri: str | None = None
    source_download_url: str | None


class TemplateAuditLawSource(ConnectorInput):
    url: HttpUrl
    title: str = Field(min_length=1, max_length=500)
    provision: str = Field(min_length=1, max_length=1000)
    excerpt: str = Field(min_length=1, max_length=10000)
    checked_at: datetime
    effective_from: date
    effective_until: date | None = None
    edition: str = Field(min_length=1, max_length=500)
    applicability: str = Field(min_length=1, max_length=3000)
    content_hash: str = Field(pattern="^[a-f0-9]{64}$")
    official: bool
    verification: Literal["verified", "unavailable", "unverified", "future"]


class TemplateAuditFindingInput(ConnectorInput):
    block_id: str = Field(min_length=1, max_length=256)
    original_text: str = Field(min_length=1, max_length=100000)
    category: Literal[
        "legal_applicability", "contradiction", "tax", "variables", "editorial"
    ]
    risk: str = Field(min_length=1, max_length=10000)
    severity: Literal["low", "medium", "high", "critical"]
    proposed_text: str | None = Field(default=None, max_length=100000)
    confidence: Literal["low", "medium", "high"]
    verification: Literal["verified", "unverified", "needs_legal_review"] = "unverified"
    sources: list[TemplateAuditLawSource] = Field(default_factory=list, max_length=20)
    applicability: str = Field(min_length=1, max_length=3000)


class TemplateAuditSaveInput(WriteInput):
    legal_entity_id: int = Field(gt=0)
    template_id: int = Field(gt=0)
    version_id: int = Field(gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    source_hash: str = Field(pattern="^[a-f0-9]{64}$")
    context_hash: str = Field(pattern="^[a-f0-9]{64}$")
    expected_revision: int = Field(default=0, ge=0)
    checked_at: datetime
    review_date: date
    checklist: dict[str, Literal["checked", "unverified", "not_applicable"]]
    findings: list[TemplateAuditFindingInput] = Field(max_length=100)
    legal_sources_hash: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")


class TemplateAuditReportReadInput(ConnectorInput):
    report_id: int = Field(gt=0)
    occurrences_finding_id: str | None = Field(default=None, max_length=64)
    occurrences_page: int = Field(default=1, ge=1)
    legal_sources_hash: str | None = Field(default=None, pattern="^[a-f0-9]{64}$")


class TemplateAuditReportResult(BaseModel):
    id: int
    template_id: int
    template_name: str = "Шаблон"
    version_number: int = 0
    version_id: int
    legal_entity_id: int
    customer_id: int | None
    revision: int
    source_hash: str
    context_hash: str
    legal_sources_hash: str
    checked_at: datetime
    coverage: dict[str, Any]
    checklist: dict[str, str]
    findings: list[dict[str, Any]]
    proposals: list[dict[str, Any]]
    stale: bool
    stale_reasons: list[str]
    legal_currency: Literal[
        "matches_supplied_hash", "changed", "requires_external_recheck"
    ]
    manager_url: str


class TemplateAuditEdit(ConnectorInput):
    finding_id: str = Field(min_length=1, max_length=64)
    block_id: str = Field(min_length=1, max_length=256)
    expected_text: str = Field(min_length=1, max_length=100000)
    replacement_text: str = Field(max_length=100000)
    reason: str = Field(min_length=1, max_length=3000)


class TemplateAuditProposalInput(WriteInput):
    report_id: int = Field(gt=0)
    expected_revision: int = Field(ge=1)
    source_hash: str = Field(pattern="^[a-f0-9]{64}$")
    context_hash: str = Field(pattern="^[a-f0-9]{64}$")
    legal_sources_hash: str = Field(pattern="^[a-f0-9]{64}$")
    edits: list[TemplateAuditEdit] = Field(min_length=1, max_length=50)


class TemplateAuditDecisionInput(ConnectorInput):
    expected_revision: int = Field(ge=1)
    source_hash: str = Field(pattern="^[a-f0-9]{64}$")
    context_hash: str = Field(pattern="^[a-f0-9]{64}$")
    legal_sources_hash: str = Field(pattern="^[a-f0-9]{64}$")
    status: Literal["proposal", "needs_legal_review", "accepted", "rejected", "fixed"]
    reason: str = Field(min_length=1, max_length=3000)


class TemplateAuditPreviewInput(ConnectorInput):
    synthetic: Literal[True]
    label: str = Field(min_length=1, max_length=200)
    values: dict[str, str]
    conditions: dict[str, bool]
    table_rows: dict[str, list[dict[str, str]]] = Field(default_factory=dict)
    format: Literal["docx", "pdf"] = "pdf"
    source_hash: str = Field(pattern="^[a-f0-9]{64}$")
    context_hash: str = Field(pattern="^[a-f0-9]{64}$")
    legal_sources_hash: str = Field(pattern="^[a-f0-9]{64}$")


class TemplateAuditPreviewContext(TemplateAuditPreviewInput):
    field_labels: dict[str, str]
    condition_labels: dict[str, str]
    table_labels: dict[str, str]
    row_field_labels: dict[str, str]


class TemplateAuditReportList(BaseModel):
    items: list[TemplateAuditReportResult]
    total: int
    page: int
    limit: int
