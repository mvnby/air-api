"""Public and Manager lead API contracts."""

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, field_validator

from core.input_validation import (
    validate_optional_bic,
    validate_optional_email,
    validate_optional_iban,
    validate_optional_phone,
    validate_optional_unp,
    validate_required_phone,
)
from schemas_common import Meta


class ProductAvailabilityLeadPayload(BaseModel):
    product_id: int
    phone: str
    name: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        return validate_required_phone(value)


class ProductAvailabilityLeadResponse(BaseModel):
    lead_id: int
    status: str
    created_at: datetime


class LeadResponse(BaseModel):
    id: int
    status: str
    source: str
    segment_hint: str
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    inn: Optional[str] = None
    company_name: Optional[str] = None
    request_text: str
    source_message_id: Optional[str] = None
    source_fingerprint: Optional[str] = None
    loss_reason: Optional[str] = None
    next_followup_date: Optional[datetime] = None
    archived_at: Optional[datetime] = None
    converted_order_id: Optional[int] = None
    created_at: datetime
    updated_at: Optional[datetime] = None


class LeadListResponse(BaseModel):
    items: List[LeadResponse]
    meta: Meta


class LeadCreatePayload(BaseModel):
    source: str = "manager"
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    inn: Optional[str] = None
    company_name: Optional[str] = None
    segment_hint: Optional[str] = None
    request_text: str
    source_message_id: Optional[str] = None
    source_fingerprint: Optional[str] = None
    next_followup_date: Optional[datetime] = None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_phone(value)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_email(value)

    @field_validator("inn")
    @classmethod
    def _validate_inn(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_unp(value)


class LeadUpdatePayload(BaseModel):
    status: Optional[str] = None
    source: Optional[str] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    inn: Optional[str] = None
    company_name: Optional[str] = None
    segment_hint: Optional[str] = None
    request_text: Optional[str] = None
    source_message_id: Optional[str] = None
    source_fingerprint: Optional[str] = None
    loss_reason: Optional[str] = None
    next_followup_date: Optional[datetime] = None
    archived_at: Optional[datetime] = None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_phone(value)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_email(value)

    @field_validator("inn")
    @classmethod
    def _validate_inn(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_unp(value)


class LeadQualifyPayload(BaseModel):
    customer_id: Optional[int] = None
    customer_branch_id: Optional[int] = None
    name: Optional[str] = None
    phone: Optional[str] = None
    email: Optional[str] = None
    inn: Optional[str] = None
    full_legal_name: Optional[str] = None
    legal_address: Optional[str] = None
    iban: Optional[str] = None
    bic: Optional[str] = None
    bank_name: Optional[str] = None
    delivery_address: Optional[str] = None
    customer_type: Optional[str] = None
    order_comment: Optional[str] = None

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_phone(value)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_email(value)

    @field_validator("inn")
    @classmethod
    def _validate_inn(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_unp(value)

    @field_validator("iban")
    @classmethod
    def _validate_iban(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_iban(value)

    @field_validator("bic")
    @classmethod
    def _validate_bic(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_bic(value)


class LeadLossPayload(BaseModel):
    status: str = "lost"
    loss_reason: Optional[str] = None


class LeadQualifyResponse(BaseModel):
    lead: LeadResponse
    customer_id: int
    order_id: int
