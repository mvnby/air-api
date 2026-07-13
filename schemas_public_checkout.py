"""Strict public checkout and contact command contracts.

Kept outside the legacy schema registry so the public boundary can evolve
without adding more unrelated responsibilities to ``schemas.py``.
"""

from datetime import datetime
from typing import Annotated, List, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from core.input_validation import (
    validate_optional_bic,
    validate_optional_email,
    validate_optional_iban,
    validate_optional_unp,
    validate_required_phone,
)


PublicInstallationOptionSlug = Annotated[
    str,
    Field(
        min_length=1,
        max_length=64,
        pattern=r"^[a-z0-9]+(?:[-_][a-z0-9]+)*$",
    ),
]


class InstallationMetaPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    source: Optional[str] = Field(default=None, max_length=64)
    type: Optional[str] = Field(default=None, max_length=100)
    meters: float = Field(default=3, ge=1, le=50, allow_inf_nan=False, strict=True)
    power_range: Optional[str] = Field(default=None, max_length=120)


class CartItemPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: Optional[int] = Field(default=None, gt=0, strict=True)
    quantity: int = Field(default=1, ge=1, le=20, strict=True)
    with_installation: bool = Field(default=False, strict=True)
    installation_rate_id: Optional[int] = Field(default=None, gt=0, strict=True)
    # Compatibility-only quote hint. The public checkout pricing service never
    # treats this client-controlled number as authoritative.
    installation_price: float = Field(default=0.0, allow_inf_nan=False, strict=True)
    installation_meta: Optional[InstallationMetaPayload] = None
    installation_options: List[PublicInstallationOptionSlug] = Field(
        default_factory=list,
        max_length=20,
    )

    @field_validator("installation_options")
    @classmethod
    def _validate_unique_installation_options(cls, value: List[str]) -> List[str]:
        if len(value) != len(set(value)):
            raise ValueError("Опции монтажа не должны повторяться")
        return value

    @model_validator(mode="after")
    def _validate_item_kind(self):
        if self.product_id is None:
            if not self.with_installation or self.installation_rate_id is None:
                raise ValueError(
                    "Позиция без товара допустима только для монтажа с installation_rate_id"
                )
            return self

        if not self.with_installation and (
            self.installation_rate_id is not None
            or self.installation_meta is not None
            or self.installation_options
        ):
            raise ValueError("Параметры монтажа требуют with_installation=true")
        return self


class CustomerPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=7, max_length=40)
    email: Optional[str] = Field(default=None, max_length=254)
    address: Optional[str] = Field(default=None, max_length=500)
    type: Literal["individual", "company"] = "individual"
    full_legal_name: Optional[str] = Field(default=None, max_length=300)
    inn: Optional[str] = Field(default=None, max_length=32)
    legal_address: Optional[str] = Field(default=None, max_length=500)
    iban: Optional[str] = Field(default=None, max_length=64)
    bic: Optional[str] = Field(default=None, max_length=32)
    bank_name: Optional[str] = Field(default=None, max_length=300)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        return validate_required_phone(value)

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


class OrderPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_default=True)

    customer: CustomerPayload
    items: List[CartItemPayload] = Field(min_length=1, max_length=20)
    comment: Optional[str] = Field(default=None, max_length=2000)


class OrderResponse(BaseModel):
    id: int
    status: str
    total_amount: float
    created_at: datetime


class PublicOrderPricingErrorDetail(BaseModel):
    code: str
    message: str


class PublicOrderPricingErrorResponse(BaseModel):
    detail: PublicOrderPricingErrorDetail


class PublicContactLeadPayload(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=7, max_length=40)
    email: Optional[str] = Field(default=None, max_length=254)
    address: Optional[str] = Field(default=None, max_length=500)
    message: Optional[str] = Field(default=None, max_length=2000)

    @field_validator("phone")
    @classmethod
    def _validate_phone(cls, value: str) -> str:
        return validate_required_phone(value)

    @field_validator("email")
    @classmethod
    def _validate_email(cls, value: Optional[str]) -> Optional[str]:
        return validate_optional_email(value)


class PublicContactLeadResponse(BaseModel):
    lead_id: int
    status: str
    created_at: datetime
