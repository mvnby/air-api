"""Read-only contract for the Manager catalog decision workspace.

The supplier fields are deliberately projection fields.  Future tenant policies
must provide an eligible-offer projection; they must never reuse this system
projection and then hide columns in the browser.
"""

from typing import Literal

from pydantic import BaseModel, Field

from schemas_common import Meta


CatalogDecisionSort = Literal[
    "retail_price", "purchase_cost", "rrc", "margin_abs", "margin_pct",
    "availability", "cooling_power", "title",
]


class CatalogDecisionProductResponse(BaseModel):
    id: int
    title: str
    slug: str
    main_image: str | None = None
    brand_title: str | None = None
    series_title: str | None = None
    retail_price_byn: float
    purchase_cost_byn: float | None = None
    recommended_price_byn: float | None = None
    margin_abs_byn: float | None = None
    margin_pct: float | None = None
    supplier_name: str | None = None
    supplier_qty: int = 0
    availability: Literal["in_stock", "out_of_stock"]
    cooling_power_kw: float | None = None
    cooling_min_kw: float | None = None
    cooling_max_kw: float | None = None
    area_m2: float | None = None
    category: str | None = None
    indoor_form_factor: str | None = None
    is_inverter: bool
    wifi: Literal["builtin", "ready", "none"] = "none"
    is_published: bool


class CatalogDecisionListResponse(BaseModel):
    items: list[CatalogDecisionProductResponse] = Field(default_factory=list)
    meta: Meta


class CatalogDecisionFilterOption(BaseModel):
    id: int
    title: str
    # A series title is not globally unique ("Elite" is a common example).
    # The UI uses this ownership link to show series only beneath chosen brands.
    brand_id: int | None = None


class CatalogDecisionFilterOptionsResponse(BaseModel):
    brands: list[CatalogDecisionFilterOption] = Field(default_factory=list)
    series: list[CatalogDecisionFilterOption] = Field(default_factory=list)


class CatalogDecisionCreateCollectionPayload(BaseModel):
    title: str = Field(min_length=1, max_length=180)
    product_ids: list[int] = Field(min_length=1, max_length=24)


CatalogDecisionOrderAttachMode = Literal[
    "auto",
    "replace_selected",
    "new_alternative",
]


class CatalogDecisionAttachToOrderPayload(BaseModel):
    product_ids: list[int] = Field(min_length=1, max_length=24)
    mode: CatalogDecisionOrderAttachMode = "auto"
