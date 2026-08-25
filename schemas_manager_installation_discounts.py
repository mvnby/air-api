"""Manager contracts for catalog-product installation discount policies."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ManagerInstallationDiscountStatus(str, Enum):
    legacy = "legacy"
    active = "active"
    disabled = "disabled"
    blocked_low_margin = "blocked_low_margin"
    blocked_missing_cost = "blocked_missing_cost"


class ManagerInstallationDiscountPolicyResponse(BaseModel):
    is_enabled: bool
    default_discount: int
    minimum_margin: int


class ManagerInstallationDiscountPolicyUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_enabled: bool
    default_discount: int = Field(ge=0, le=10_000)
    minimum_margin: int = Field(ge=0, le=1_000_000)


class ManagerInstallationDiscountProductResponse(BaseModel):
    product_id: int
    title: str
    slug: str
    main_image: str | None = None
    retail_price: int
    purchase_cost: float | None = None
    margin: float | None = None
    configured_discount: int
    applied_discount: int
    has_override: bool
    status: ManagerInstallationDiscountStatus
    status_note: str


class ManagerInstallationDiscountRuleListResponse(BaseModel):
    policy: ManagerInstallationDiscountPolicyResponse
    items: list[ManagerInstallationDiscountProductResponse]
    page: int
    limit: int
    total: int


class ManagerInstallationDiscountProductSearchResponse(BaseModel):
    items: list[ManagerInstallationDiscountProductResponse]


class ManagerInstallationDiscountRuleUpdatePayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    discount_amount: int = Field(ge=0, le=10_000)
