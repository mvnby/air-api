"""Source evidence and independently reviewed commercial document terms."""
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from schemas_business_document_terms import BusinessDocumentTermsPayload


class CommercialSourceTerm(BaseModel):
    model_config = ConfigDict(extra="forbid")
    kind: Literal["payment", "delivery"]
    source: str = Field(max_length=255)
    evidence: str = Field(min_length=1, max_length=2000)
    share_percent: Decimal | None = Field(default=None, gt=0, le=100)
    due_days: int | None = Field(default=None, ge=1, le=3650)
    day_kind: Literal["calendar", "banking", "working"] | None = None
    due_event: Literal["before_supply", "before_work", "after_supply", "after_work", "after_acceptance"] | None = None
    trigger_text: str | None = Field(default=None, max_length=500)
    deadline: str | None = None
    issues: list[str] = Field(default_factory=list)


class ManagerCommercialTermsResponse(BaseModel):
    order_id: int
    revision: int = 0
    customer_requested: list[CommercialSourceTerm] = Field(default_factory=list)
    proposed: BusinessDocumentTermsPayload | None = None
    suggested: BusinessDocumentTermsPayload | None = None
    confirmed: bool = False
    warnings: list[str] = Field(default_factory=list)


class ManagerCommercialTermsUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_revision: int = Field(ge=0)
    proposed: BusinessDocumentTermsPayload
    confirmed: bool = False

    @model_validator(mode="after")
    def confirmed_schedule(self):
        if self.confirmed and not self.proposed.payment_schedule:
            raise ValueError("Для подтверждения заполните график оплаты")
        return self


class ManagerCommercialDocumentDefaults(BaseModel):
    order_id: int
    revision: int
    business_terms: BusinessDocumentTermsPayload | None = None


class ManagerCommercialTermsExtract(BaseModel):
    model_config = ConfigDict(extra="forbid")
    attachment_ids: list[int] = Field(default_factory=list, max_length=8)
