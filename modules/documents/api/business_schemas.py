from __future__ import annotations

from datetime import date
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from modules.documents.domain.business_terms import (
    CONTRACT_SCENARIOS,
    PAYMENT_DAY_KINDS,
    PAYMENT_DUE_EVENTS,
)


class PaymentScheduleItemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    share_percent: Decimal = Field(gt=0, le=100, max_digits=5, decimal_places=2)
    due_event: str = Field(pattern="^(" + "|".join(sorted(PAYMENT_DUE_EVENTS)) + ")$")
    due_days: int | None = Field(default=None, ge=1, le=3650)
    due_day_kind: str = Field(
        default="calendar",
        pattern="^(" + "|".join(sorted(PAYMENT_DAY_KINDS)) + ")$",
    )
    note: str | None = Field(default=None, max_length=1000)


class BusinessDocumentTermsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    contract_scenario: str | None = Field(
        default=None,
        pattern="^(" + "|".join(sorted(CONTRACT_SCENARIOS)) + ")$",
    )
    subject: str | None = Field(default=None, max_length=2000)
    delivery_deadline: date | None = None
    performance_deadline: date | None = None
    valid_until: date | None = None
    additional_conditions: str | None = Field(default=None, max_length=8000)
    additional_conditions_overridden: bool = False
    payment_schedule: list[PaymentScheduleItemPayload] = Field(
        default_factory=list, max_length=20
    )
    goods_warranty_months: int | None = Field(default=None, ge=0, le=240)
    goods_warranty_terms: str | None = Field(default=None, max_length=4000)
    work_warranty_months: int | None = Field(default=None, ge=0, le=240)
    work_warranty_terms: str | None = Field(default=None, max_length=4000)

    @model_validator(mode="after")
    def validate_schedule(self) -> "BusinessDocumentTermsPayload":
        if self.payment_schedule and sum(
            item.share_percent for item in self.payment_schedule
        ) != Decimal("100"):
            raise ValueError("График оплаты должен составлять ровно 100%")
        return self


class ActTermsPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    result_text: str | None = Field(default=None, max_length=8000)
    claims_status: str = Field(default="none", pattern="^(none|present)$")
    claims_text: str | None = Field(default=None, max_length=8000)
    acceptance_deadline: date | None = None

    @model_validator(mode="after")
    def validate_claims(self) -> "ActTermsPayload":
        if self.claims_status == "present" and not str(self.claims_text or "").strip():
            raise ValueError("При наличии замечаний укажите их текст")
        return self
