"""Manager review contract for Belzakupki source enrichment."""

from pydantic import BaseModel, Field, field_validator


class SourceCustomerDraft(BaseModel):
    name: str | None = Field(default=None, max_length=500)
    inn: str | None = Field(default=None, max_length=30)
    type: str = Field(default="company", max_length=40)
    phone: str | None = Field(default=None, max_length=80)
    email: str | None = Field(default=None, max_length=255)
    legal_address: str | None = Field(default=None, max_length=500)


class SourceEquipmentDraft(BaseModel):
    brand: str | None = Field(default=None, max_length=80)
    model: str | None = Field(default=None, max_length=120)
    quantity: int | None = Field(default=None, ge=1)


class SourceObjectDraft(BaseModel):
    address: str = Field(default="", max_length=500)
    equipment: list[SourceEquipmentDraft] = Field(default_factory=list, max_length=100)


class SourceEquipmentPrefillItem(BaseModel):
    brand: str | None = None
    model: str | None = None
    quantity: int | None = None
    product_id: int | None = None
    line_id: int | None = None
    reason: str
    message: str


class SourceEquipmentPrefillResult(BaseModel):
    proposal_id: int | None = None
    added: list[SourceEquipmentPrefillItem] = Field(default_factory=list)
    skipped: list[SourceEquipmentPrefillItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SourceEquipmentCandidateItem(BaseModel):
    brand: str | None = None
    model: str | None = None
    quantity: int | None = None
    product_id: int | None = None
    product_title: str | None = None
    price: int | None = None
    available_quantity: int | None = None
    existing_quantity: int = 0
    reason: str
    message: str
    can_add: bool = False
    can_restore: bool = False


class ManagerOrderSourceEquipmentPreview(BaseModel):
    order_id: int
    proposal_id: int | None = None
    proposal_status: str | None = None
    preview_fingerprint: str
    items: list[SourceEquipmentCandidateItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ManagerOrderSourceEquipmentAdd(BaseModel):
    proposal_id: int
    command_id: str = Field(min_length=1, max_length=120)
    preview_fingerprint: str = Field(min_length=64, max_length=64)
    product_ids: list[int] = Field(min_length=1, max_length=100)
    restore_removed_product_ids: list[int] = Field(default_factory=list, max_length=100)


class SourceOriginalFile(BaseModel):
    attachment_id: int
    name: str
    document_id: str | None = None
    mime_type: str


class SourceInstallationFact(BaseModel):
    text: str
    source: str
    needs_review: bool = True
    is_excerpt: bool = False


class ManagerOrderSourceCard(BaseModel):
    order_id: int
    source: str
    external_id: str
    title: str | None = None
    source_url: str | None = None
    work_summary: str | None = None
    equipment_details: str | None = None
    objects: list[SourceObjectDraft] = Field(default_factory=list)
    originals: list[SourceOriginalFile] = Field(default_factory=list)
    equipment_prefill: SourceEquipmentPrefillResult | None = None
    installation_facts: list[SourceInstallationFact] = Field(default_factory=list)


class SourceDocumentPreview(BaseModel):
    id: str
    name: str
    source_url: str | None = None
    extracted_text: str | None = None
    extracted_text_truncated: bool = False
    download_url: str


class SourceScenarioDraft(BaseModel):
    workflow_type: str
    service_type: str | None = None
    label: str


class ManagerOrderSourcePreview(BaseModel):
    order_id: int
    source_code: str
    external_id: str
    source_url: str | None = None
    title: str | None = None
    deadline_at: str | None = None
    estimated_value: float | None = None
    customer: SourceCustomerDraft
    existing_customer_id: int | None = None
    current_scenario: SourceScenarioDraft | None = None
    suggested_scenario: SourceScenarioDraft | None = None
    work_summary: str | None = None
    equipment_details: str | None = None
    objects: list[SourceObjectDraft] = Field(default_factory=list)
    documents: list[SourceDocumentPreview] = Field(default_factory=list)
    field_sources: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    analysis_source: str = "source"
    analyzed_document_ids: list[str] = Field(default_factory=list)
    equipment_prefill: SourceEquipmentPrefillResult | None = None


class ManagerOrderSourceAnalyze(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=8)


class ManagerOrderSourceApply(BaseModel):
    customer_action: str
    customer_id: int | None = None
    customer: SourceCustomerDraft | None = None
    workflow_type: str | None = None
    service_type: str | None = None
    work_summary: str | None = Field(default=None, max_length=10000)
    equipment_details: str | None = Field(default=None, max_length=10000)
    objects: list[SourceObjectDraft] | None = Field(default=None, max_length=30)
    document_ids: list[str] = Field(default_factory=list, max_length=8)
    analysis_source: str | None = None
    analyzed_document_ids: list[str] | None = None

    @field_validator("customer_action")
    @classmethod
    def validate_action(cls, value: str) -> str:
        if value not in {"existing", "create", "skip"}:
            raise ValueError("customer_action must be existing, create or skip")
        return value

    @field_validator("analysis_source")
    @classmethod
    def validate_analysis_source(cls, value: str | None) -> str | None:
        if value is not None and value not in {"source", "ai", "reviewed"}:
            raise ValueError("analysis_source must be source, ai or reviewed")
        return value


class ManagerOrderSourceApplyResult(BaseModel):
    order_id: int
    customer_id: int | None = None
    attachment_ids: list[int] = Field(default_factory=list)
    applied_fields: list[str] = Field(default_factory=list)
    equipment_prefill: SourceEquipmentPrefillResult | None = None


class ManagerOrderSourceEnrichment(BaseModel):
    source: str
    external_id: str
    work_summary: str | None = None
    equipment_details: str | None = None
    objects: list[SourceObjectDraft] = Field(default_factory=list)
    equipment_prefill: SourceEquipmentPrefillResult | None = None
    customer_branch_ids: list[int] = Field(default_factory=list)
    analysis_source: str | None = None
    analyzed_document_ids: list[str] = Field(default_factory=list)
