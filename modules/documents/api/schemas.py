from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field


class DocumentLegalEntityRequisites(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_address: str | None = Field(default=None, max_length=500)
    postal_address: str | None = Field(default=None, max_length=500)
    bank_name: str | None = Field(default=None, max_length=300)
    iban: str | None = Field(default=None, max_length=64)
    bic: str | None = Field(default=None, max_length=32)
    director_title: str | None = Field(default=None, max_length=160)
    director_name: str | None = Field(default=None, max_length=200)
    acts_on_basis: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=254)


class DocumentLegalEntityCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str = Field(min_length=1, max_length=200)
    slug: str | None = Field(default=None, max_length=80)
    legal_name: str | None = Field(default=None, max_length=500)
    unp: str | None = Field(default=None, max_length=32)
    entity_type: str = Field(
        default="organization",
        pattern="^(organization|individual_entrepreneur)$",
    )
    is_vat_payer: bool = False
    is_default: bool = False
    requisites: DocumentLegalEntityRequisites = Field(
        default_factory=DocumentLegalEntityRequisites
    )


class DocumentLegalEntityUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    slug: str | None = Field(default=None, min_length=1, max_length=80)
    legal_name: str | None = Field(default=None, max_length=500)
    unp: str | None = Field(default=None, max_length=32)
    entity_type: str | None = Field(
        default=None,
        pattern="^(organization|individual_entrepreneur)$",
    )
    is_vat_payer: bool | None = None
    is_default: bool | None = None
    requisites: DocumentLegalEntityRequisites | None = None
    status: str | None = Field(default=None, pattern="^(active|disabled)$")


class DocumentLegalEntityItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    slug: str
    display_name: str
    legal_name: str | None = None
    unp: str | None = None
    entity_type: str
    is_vat_payer: bool
    is_default: bool
    requisites: dict[str, str]
    status: str
    created_at: datetime
    updated_at: datetime


class DocumentLegalEntityListResponse(BaseModel):
    items: list[DocumentLegalEntityItem]


class DocumentNumberPolicyItem(BaseModel):
    legal_entity_id: int
    document_type: str
    series: str
    period_mode: str
    minimum_width: int
    persisted: bool


class DocumentNumberPolicyListResponse(BaseModel):
    items: list[DocumentNumberPolicyItem]


class DocumentNumberPolicyPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    series: str = Field(default="", max_length=64)
    period_mode: str = Field(pattern="^(calendar_year|continuous|per_basis)$")
    minimum_width: int = Field(default=3, ge=1, le=12)


class NativeDocumentTemplateCreatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_entity_id: int = Field(gt=0)
    name: str = Field(min_length=1, max_length=200)
    doc_type: str = Field(pattern="^(offer|invoice|contract|act|tn2|ttn1)$")
    description: str | None = Field(default=None, max_length=1000)


class NativeDocumentTemplateItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    tenant_id: int
    legal_entity_id: int
    name: str
    doc_type: str
    description: str | None = None
    is_default: bool
    is_active: bool
    sort_order: int
    created_at: datetime


class NativeDocumentTemplateListResponse(BaseModel):
    items: list[NativeDocumentTemplateItem]


class NativeTemplateTableBlockPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(pattern="^[a-z][a-z0-9_]*$")
    row_fields: list[str] = Field(min_length=1, max_length=100)


class NativeTemplatePlaceholderSchemaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fields: list[str] = Field(default_factory=list, max_length=500)
    tables: list[NativeTemplateTableBlockPayload] = Field(
        default_factory=list, max_length=20
    )


class NativeTemplateVersionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    template_id: int
    version: int
    status: str
    renderer: str
    source_filename: str | None = None
    checksum_sha256: str
    placeholder_schema: dict
    change_note: str | None = None
    activated_at: datetime | None = None
    created_at: datetime


class NativeTemplateVersionListResponse(BaseModel):
    items: list[NativeTemplateVersionItem]


class NativePlaceholderDescriptorItem(BaseModel):
    name: str
    label: str
    group: str
    syntax: str


class NativePlaceholderTableItem(BaseModel):
    name: str
    anchor_syntax: str
    row_fields: list[NativePlaceholderDescriptorItem]


class NativePlaceholderCatalogResponse(BaseModel):
    document_type: str
    fields: list[NativePlaceholderDescriptorItem]
    tables: list[NativePlaceholderTableItem]


class ManagedDocumentDraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_entity_id: int = Field(gt=0)
    document_type: str = Field(pattern="^(offer|invoice|contract|act|tn2|ttn1)$")
    issue_date: date
    template_id: int | None = Field(default=None, gt=0)
    proposal_id: int | None = Field(default=None, gt=0)
    base_document_id: int | None = Field(default=None, gt=0)
    base_customer_contract_id: int | None = Field(default=None, gt=0)
    scope_customer_branch_id: int | None = Field(default=None, gt=0)
    scope_title: str | None = Field(default=None, max_length=500)
    scope_address: str | None = Field(default=None, max_length=1000)
    scope_service_line_ids: list[int] = Field(default_factory=list, max_length=500)
    scope_service_line_quantities: dict[int, int] = Field(default_factory=dict)
    scope_product_line_ids: list[int] = Field(default_factory=list, max_length=500)
    business_role: str | None = Field(default=None, pattern="^(payment_request|offer)$")
    replaces_document_id: int | None = Field(default=None, gt=0)


class ManagedDocumentVoidPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=1, max_length=1000)


class ManagedDocumentArtifactItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    order_document_id: int
    kind: str
    content_type: str
    filename: str
    checksum_sha256: str
    size_bytes: int
    created_at: datetime


class ManagedDocumentArtifactListResponse(BaseModel):
    items: list[ManagedDocumentArtifactItem]


class ManagedDocumentArtifactAccessResponse(BaseModel):
    url: str
    expires_in: int


class ManagedDocumentItem(BaseModel):
    id: int
    order_id: int
    legal_entity_id: int | None = None
    proposal_id: int | None = None
    doc_type: str
    business_role: str | None = None
    status: str
    provider: str
    internal_reference: str | None = None
    official_series: str | None = None
    official_period_key: str | None = None
    official_number: str | None = None
    official_full_number: str | None = None
    official_date: date | None = None
    display_number: str
    date: datetime
    document_template_id: int | None = None
    template_version_id: int | None = None
    base_document_id: int | None = None
    base_customer_contract_id: int | None = None
    replaces_document_id: int | None = None
    issued_at: datetime | None = None
    sent_at: datetime | None = None
    signed_at: datetime | None = None
    voided_at: datetime | None = None
    void_reason: str | None = None
    google_edit_url: str | None = None
    created_at: datetime
    artifacts: list[ManagedDocumentArtifactItem] = Field(default_factory=list)


class ManagedDocumentListResponse(BaseModel):
    items: list[ManagedDocumentItem]


class DocumentPdfRuntimeStatus(BaseModel):
    available: bool
    provider: str
    detail: str
