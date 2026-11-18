"""MCP projections for a tender's private document inventory and qualification."""

from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, Field, model_validator

from schemas_connector_mcp import OrderIdInput
from schemas_tender_qualification import TenderQualificationProfile, TenderQualificationResult


class TenderReviewInput(OrderIdInput):
    source_reference: str | None = Field(default=None, pattern=r"^[0-9a-f]{64}$",
                                         description="Native source reference from list_tender_inbox. Defaults to the current publication.")


class TenderSourcePreviewInput(TenderReviewInput):
    page: int = Field(default=1, ge=1, le=10000)
    limit: int = Field(default=20, ge=1, le=50)


class TenderDocumentInfo(BaseModel):
    document_id: str
    filename: str
    mime_type: str | None = None
    saved_original: bool = False
    has_source_text: bool | None = None
    source_text_truncated: bool | None = None
    source_error: str | None = None


class TenderLot(BaseModel):
    number: str | None = None
    title: str | None = None
    quantity: str | None = None
    execution_address: str | None = None
    estimated_value: str | None = None


class TenderSourcePreviewResult(BaseModel):
    order_id: int
    manager_url: str
    source: str
    external_id: str
    source_url: str | None
    title: str | None
    customer: str | None
    deadline_at: AwareDatetime | None
    deadline_kind: str | None
    estimated_value: str | None
    currency: str | None
    procedure_type: str | None
    submission_method: str
    submission_email: str | None
    execution_addresses: list[str]
    lots: list[TenderLot]
    total_lots: int
    documents: list[TenderDocumentInfo]
    total_documents: int
    inventory_complete: bool
    page: int
    next_page: int | None
    warnings: list[str]


class AnalyzeTenderInput(TenderReviewInput):
    provider: Literal["openai", "deepseek"] = "openai"
    document_ids: list[Annotated[str, Field(min_length=1, max_length=300)]] = Field(min_length=1, max_length=8)
    profile_name: Literal["mvn_vitebsk"] | None = None
    profile: TenderQualificationProfile | None = None

    @model_validator(mode="after")
    def validate_selection(self):
        if len(set(self.document_ids)) != len(self.document_ids):
            raise ValueError("Select each document once")
        if self.profile_name and self.profile:
            raise ValueError("Select one qualification profile")
        return self


class AnalyzedTenderFile(BaseModel):
    document_id: str
    filename: str | None
    sha256: str | None = None
    origin: str | None = None
    status: str
    diagnostics: list[str] = Field(default_factory=list)


class AnalyzeTenderResult(BaseModel):
    source: str
    external_id: str
    order_id: int
    manager_url: str
    documents: list[AnalyzedTenderFile]
    unselected_count: int
    inventory_complete: bool
    warnings: list[str]
    qualification: TenderQualificationResult
