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
    address: str = Field(min_length=1, max_length=500)
    equipment: list[SourceEquipmentDraft] = Field(default_factory=list, max_length=100)


class SourceDocumentPreview(BaseModel):
    id: str
    name: str
    source_url: str | None = None
    extracted_text: str | None = None
    extracted_text_truncated: bool = False
    download_url: str


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
    work_summary: str | None = None
    equipment_details: str | None = None
    objects: list[SourceObjectDraft] = Field(default_factory=list)
    documents: list[SourceDocumentPreview] = Field(default_factory=list)
    field_sources: dict[str, str] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    analysis_source: str = "source"
    analyzed_document_ids: list[str] = Field(default_factory=list)


class ManagerOrderSourceAnalyze(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=8)


class ManagerOrderSourceApply(BaseModel):
    customer_action: str
    customer_id: int | None = None
    customer: SourceCustomerDraft | None = None
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


class ManagerOrderSourceEnrichment(BaseModel):
    source: str
    external_id: str
    work_summary: str | None = None
    equipment_details: str | None = None
    objects: list[SourceObjectDraft] = Field(default_factory=list)
    customer_branch_ids: list[int] = Field(default_factory=list)
    analysis_source: str | None = None
    analyzed_document_ids: list[str] = Field(default_factory=list)
