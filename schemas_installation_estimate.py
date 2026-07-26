"""Public contract for preliminary installation estimates from customer photos."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from core.input_validation import validate_optional_email, validate_required_phone


class InstallationEstimateLeadPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=7, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    address: str | None = Field(default=None, max_length=500)
    description: str | None = Field(default=None, max_length=2000)
    object_type: Literal["apartment", "house", "office", "commercial", "other"] | None = None
    consent: Literal[True]

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        return validate_required_phone(value)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: str | None) -> str | None:
        return validate_optional_email(value)


class InstallationEstimateLeadResponse(BaseModel):
    lead_id: int
    order_id: int
    status: str
    created_at: datetime
    attachment_count: int
    preliminary_estimate_status: Literal["pending_review"] = "pending_review"
    replayed: bool = False
