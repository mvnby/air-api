"""Closed API contracts for tenant service-template copying and public pricing."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas import (
    ManagerEstimateRuleInputPayload,
    ManagerTariffRuleType,
    ManagerTariffServiceKind,
)


class ServiceCatalogCounts(BaseModel):
    services: int = 0
    tariffs: int = 0
    tariff_rules: int = 0
    installation_rates: int = 0


class ManagerServiceCatalogTemplatePreviewResponse(BaseModel):
    source_counts: ServiceCatalogCounts
    source_fingerprint: str
    target_counts: ServiceCatalogCounts
    can_clone: bool


class ManagerServiceCatalogClonePayload(BaseModel):
    expected_fingerprint: str = Field(min_length=64, max_length=64)


class ManagerServiceCatalogCloneResponse(BaseModel):
    status: Literal["cloned", "already_cloned"]
    cloned_counts: ServiceCatalogCounts
    source_fingerprint: str


class PublicServiceTariffRuleResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    rule_type: ManagerTariffRuleType
    name: str
    line_template: str
    unit: str
    unit_price: float
    is_optional: bool
    sort_order: int


class PublicServiceTariffResponse(BaseModel):
    id: int
    service_kind: ManagerTariffServiceKind
    short_name: str
    full_description: str | None = None
    category: str
    power_range: str
    base_price: int
    included_route_meters: float
    rules: list[PublicServiceTariffRuleResponse] = Field(default_factory=list)


class PublicServiceTariffListResponse(BaseModel):
    items: list[PublicServiceTariffResponse]


class PublicServiceEstimateCalculatePayload(BaseModel):
    tariff_id: int = Field(ge=1)
    route_length_m: float = 3.0
    quantity: int = 1
    extra_holes_count: int = 0
    rule_inputs: list[ManagerEstimateRuleInputPayload] = Field(default_factory=list)

    @field_validator("route_length_m")
    @classmethod
    def validate_route_length(cls, value: float) -> float:
        if value < 0:
            raise ValueError("route_length_m must be >= 0")
        return value

    @field_validator("quantity")
    @classmethod
    def validate_quantity(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("quantity must be greater than zero")
        return value

    @field_validator("extra_holes_count")
    @classmethod
    def validate_holes(cls, value: int) -> int:
        if value < 0:
            raise ValueError("extra_holes_count must be >= 0")
        return value
