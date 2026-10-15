from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api_contracts.catalog_decision import CatalogDecisionProductResponse
from schemas_common import Meta


class ManagerTenantCatalogProductResponse(BaseModel):
    id: int
    title: str
    slug: str
    brand_title: str | None = None
    series_title: str | None = None
    main_image: str | None = None
    product_kind: str
    is_inverter: bool
    power_cooling: float | None = None
    offer_id: int | None = None
    offer_status: Literal["active", "disabled"] | None = None
    offer_is_published: bool | None = None
    effective_price: int | None = None
    allowed: bool


class ManagerTenantCatalogListResponse(BaseModel):
    items: list[ManagerTenantCatalogProductResponse] = Field(default_factory=list)
    meta: Meta


class ManagerTenantCatalogSpecificationResponse(BaseModel):
    key: str
    label: str
    value: str
    unit: str | None = None


class ManagerTenantCatalogSpecificationGroupResponse(BaseModel):
    key: str
    label: str
    items: list[ManagerTenantCatalogSpecificationResponse] = Field(default_factory=list)


class ManagerTenantCatalogImageResponse(BaseModel):
    url: str
    alt: str | None = None


class ManagerTenantCatalogManualResponse(BaseModel):
    title: str
    url: str


class ManagerTenantCatalogProductDetailResponse(BaseModel):
    """Shared product content with only the current storefront's commercial view."""

    id: int
    title: str
    slug: str
    brand_title: str | None = None
    series_title: str | None = None
    main_image: str | None = None
    description: str = Field(default="", description="Plain text; render as text, never HTML.")
    images: list[ManagerTenantCatalogImageResponse] = Field(default_factory=list)
    summary_fields: list[ManagerTenantCatalogSpecificationResponse] = Field(default_factory=list)
    specification_groups: list[ManagerTenantCatalogSpecificationGroupResponse] = Field(default_factory=list)
    manuals: list[ManagerTenantCatalogManualResponse] = Field(default_factory=list)
    effective_price: int | None = None
    allowed: bool
    selection_item: CatalogDecisionProductResponse | None = Field(
        default=None,
        description="Current eligible decision projection; absent when selection is unavailable.",
    )
