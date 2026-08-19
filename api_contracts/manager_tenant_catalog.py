from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

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
