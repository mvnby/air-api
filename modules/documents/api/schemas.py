from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.documents.domain import (
    B2C_NATIVE_DOCUMENT_TYPES,
    BUSINESS_TERMS_DOCUMENT_TYPES,
    SUPPORTED_NATIVE_DOCUMENT_TYPES,
)
from .business_schemas import ActTermsPayload, BusinessDocumentTermsPayload


NATIVE_DOCUMENT_TYPE_PATTERN = (
    "^(" + "|".join(sorted(SUPPORTED_NATIVE_DOCUMENT_TYPES)) + ")$"
)


class DocumentLegalEntityRequisites(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_address: str | None = Field(default=None, max_length=500)
    postal_address: str | None = Field(default=None, max_length=500)
    city: str | None = Field(default=None, max_length=160)
    bank_name: str | None = Field(default=None, max_length=300)
    iban: str | None = Field(default=None, max_length=64)
    bic: str | None = Field(default=None, max_length=32)
    signing_mode: str | None = Field(
        default=None,
        pattern="^(self|statutory_body|power_of_attorney)$",
    )
    signer_position: str | None = Field(default=None, max_length=160)
    signer_name: str | None = Field(default=None, max_length=200)
    acting_basis: str | None = Field(default=None, max_length=300)
    # Transitional aliases accepted from the first native-document release.
    director_title: str | None = Field(default=None, max_length=160)
    director_name: str | None = Field(default=None, max_length=200)
    acts_on_basis: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=254)
    offer_url: str | None = Field(default=None, max_length=1000)
    offer_version: str | None = Field(default=None, max_length=100)
    offer_published_on: str | None = Field(
        default=None,
        max_length=10,
        pattern=r"^\d{2}\.\d{2}\.\d{4}$",
    )
    default_goods_warranty_months: int = Field(default=36, ge=0, le=240)
    default_work_warranty_months: int | None = Field(default=None, ge=0, le=240)


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
    doc_type: str = Field(pattern=NATIVE_DOCUMENT_TYPE_PATTERN)
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
    conditions: list[str] = Field(default_factory=list, max_length=100)
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


class NativePlaceholderConditionItem(BaseModel):
    name: str
    label: str
    group: str
    start_syntax: str
    end_syntax: str


class NativePlaceholderCatalogResponse(BaseModel):
    document_type: str
    fields: list[NativePlaceholderDescriptorItem]
    conditions: list[NativePlaceholderConditionItem]
    tables: list[NativePlaceholderTableItem]


class ManagedDocumentDraftPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    legal_entity_id: int = Field(gt=0)
    document_type: str = Field(pattern=NATIVE_DOCUMENT_TYPE_PATTERN)
    issue_date: date
    issue_city: str | None = Field(default=None, max_length=160)
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
    consumer_terms: "ConsumerDocumentTermsPayload | None" = None
    business_terms: BusinessDocumentTermsPayload | None = None
    act_terms: ActTermsPayload | None = None

    @model_validator(mode="after")
    def validate_terms_scope(self) -> "ManagedDocumentDraftPayload":
        if (
            self.consumer_terms is not None
            and self.document_type not in B2C_NATIVE_DOCUMENT_TYPES
        ):
            raise ValueError(
                "Параметры документа физлицу доступны только для B2C заказ-актов"
            )
        if (
            self.business_terms is not None
            and self.document_type in B2C_NATIVE_DOCUMENT_TYPES
        ):
            raise ValueError("Параметры B2B нельзя передать для B2C заказ-акта")
        if (
            self.business_terms is not None
            and self.document_type not in BUSINESS_TERMS_DOCUMENT_TYPES
        ):
            raise ValueError(
                "Параметры B2B доступны только для договора, счета, предложения или акта"
            )
        if self.document_type == "contract" and self.business_terms is None:
            raise ValueError("Для договора выберите сценарий и условия")
        if self.business_terms is not None and self.document_type == "contract":
            if self.business_terms.contract_scenario is None:
                raise ValueError("Для договора выберите сценарий")
            if not self.business_terms.payment_schedule:
                raise ValueError("Для договора укажите график оплаты")
        elif (
            self.business_terms is not None
            and self.business_terms.contract_scenario is not None
        ):
            raise ValueError("Сценарий договора можно указать только для договора")
        if self.act_terms is not None and self.document_type != "act":
            raise ValueError("Параметры акта доступны только для акта")
        if self.document_type == "act" and self.act_terms is None:
            raise ValueError(
                "Для акта явно укажите наличие или отсутствие замечаний"
            )
        return self


class ConsumerDocumentTermsPayload(BaseModel):
    """B2C-only facts frozen on draft creation, never read from mutable CRM state."""

    model_config = ConfigDict(extra="forbid")

    equipment_brand: str | None = Field(default=None, max_length=200)
    equipment_model: str | None = Field(default=None, max_length=300)
    equipment_serial: str | None = Field(default=None, max_length=300)
    goods_warranty_months: int | None = Field(default=None, ge=0, le=240)
    goods_warranty_terms: str | None = Field(default=None, max_length=4_000)
    work_warranty_months: int | None = Field(default=None, ge=0, le=240)
    work_warranty_terms: str | None = Field(default=None, max_length=4_000)
    route_length_meters: str | None = Field(default=None, max_length=64)
    route_liquid_pipe_diameter_mm: str | None = Field(default=None, max_length=64)
    route_gas_pipe_diameter_mm: str | None = Field(default=None, max_length=64)
    route_drainage: str | None = Field(default=None, max_length=500)
    route_power_supply: str | None = Field(default=None, max_length=500)
    route_notes: str | None = Field(default=None, max_length=4_000)
    route_photo_fixation_performed: bool = False
    route_pressure_test_performed: bool = False
    route_ends_capped: bool = False


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
    issue_city: str | None = None
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
