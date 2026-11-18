"""Read-only tender facts, their document evidence and profile-based fit."""

from decimal import Decimal
from typing import Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

TenderWorkType = Literal[
    "maintenance", "diagnostics", "repair", "installation", "supply_with_installation",
    "supply_only", "ventilation",
]
TenderFactKind = Literal[
    "work_scope", "equipment_count", "equipment_models", "maintenance_frequency", "maintenance_period",
    "execution_address", "installation_lines", "installation_access", "materials", "sole_proprietor_eligibility",
    "requirements", "estimated_budget", "offer_price", "submission_method", "submission_deadline",
    "procedure_type", "logistics",
]
TenderDecision = Literal["recommend", "review", "skip"]
TenderConfidence = Literal["high", "medium", "low"]
TenderAnalysisProvider = Literal["openai", "deepseek"]
TenderExtractionStatus = Literal["completed", "local_evidence_only", "not_requested"]


class TenderDocumentFragment(BaseModel):
    document_id: str = Field(min_length=1, max_length=300)
    filename: str = Field(min_length=1, max_length=500)
    text: str
    location: str | None = Field(default=None, max_length=300)
    document_sha256: str | None = Field(default=None, pattern=r"^[0-9a-fA-F]{64}$")
    partial: bool = False


class TenderQualificationProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    service_priorities: dict[TenderWorkType, int] = Field(default_factory=dict, max_length=7)
    preferred_locations: list[str] = Field(default_factory=list, max_length=30)
    travel_locations: list[str] = Field(default_factory=list, max_length=50)
    review_only_locations: dict[TenderWorkType, list[str]] = Field(default_factory=dict, max_length=7)
    minimum_travel_budget_byn: Decimal | None = Field(default=None, ge=0, max_digits=15, decimal_places=2)
    require_sole_proprietor_eligibility: bool = False

    @classmethod
    def _valid_terms(cls, values: list[str]) -> bool:
        return len(values) <= 50 and all(2 <= len(value.strip()) <= 80 for value in values)

    @model_validator(mode="after")
    def validate_criteria(self):
        if any(not 0 <= priority <= 100 for priority in self.service_priorities.values()):
            raise ValueError("Service priorities must be from 0 to 100")
        locations = [self.preferred_locations, self.travel_locations, *self.review_only_locations.values()]
        if not all(self._valid_terms(values) for values in locations):
            raise ValueError("Location criteria must contain words of 2 to 80 characters")
        return self


class TenderQualificationSourceMetadata(BaseModel):
    """Structured portal data, mapped by the caller from the trusted source record."""

    model_config = ConfigDict(extra="forbid")

    procedure_type: str | None = Field(default=None, max_length=120)
    estimated_budget: Decimal | None = Field(default=None, ge=0, max_digits=17, decimal_places=2)
    budget_currency: str | None = Field(default=None, pattern=r"^[A-Za-z]{3}$")
    submission_deadline: AwareDatetime | None = None
    submission_method: str | None = Field(default=None, max_length=255)
    execution_addresses: list[str] = Field(default_factory=list, max_length=20)

    @model_validator(mode="after")
    def validate_addresses(self):
        if any(not 2 <= len(address.strip()) <= 700 for address in self.execution_addresses):
            raise ValueError("Execution addresses must contain 2 to 700 characters")
        return self


class TenderEvidence(BaseModel):
    document_id: str
    filename: str
    location: str | None = None
    document_sha256: str | None = None
    quote: str
    start: int
    end: int


class TenderQualificationFact(BaseModel):
    kind: TenderFactKind
    value: str
    evidence: TenderEvidence | None = None
    source: Literal["document", "procedure_metadata"] = "document"
    confidence: TenderConfidence
    work_type: TenderWorkType | None = None
    work_required: bool | None = None
    amount: Decimal | None = None
    currency: str | None = None
    deadline_at: AwareDatetime | None = None


class TenderQualificationReason(BaseModel):
    code: str
    message: str
    evidence: list[TenderEvidence] = Field(default_factory=list)


class TenderQualificationResult(BaseModel):
    provider: TenderAnalysisProvider
    model: str | None = None
    extraction_status: TenderExtractionStatus
    extraction_error: str | None = None
    decision: TenderDecision
    score: int = Field(ge=0, le=100)
    confidence: TenderConfidence
    complete: bool
    facts: list[TenderQualificationFact] = Field(default_factory=list)
    reasons: list[TenderQualificationReason] = Field(default_factory=list)
    unknowns: list[TenderFactKind] = Field(default_factory=list)
