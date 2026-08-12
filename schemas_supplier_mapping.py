from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field

from schemas_common import Meta


class SupplierOfferCandidateResponse(BaseModel):
    offer_id: int
    supplier_id: int
    supplier_name: str | None = None
    source_id: int | None = None
    source_name: str | None = None
    external_id: str
    title_raw: str | None = None
    title_normalized: str | None = None
    source_url: str | None = None
    model_tokens: list[str] = Field(default_factory=list)
    qty: int = 0
    qty_raw: str | None = None
    wholesale_raw: str | None = None
    wholesale_value: float | None = None
    wholesale_currency: str | None = None
    rrc_raw: str | None = None
    rrc_byn: float | None = None
    is_active: bool
    status: Literal["current", "free", "conflict", "inactive"]
    mapping_id: int | None = None
    mapping_is_active: bool | None = None
    mapped_product_id: int | None = None
    mapped_product_title: str | None = None
    mapped_product_slug: str | None = None
    mapped_by: str | None = None
    mapped_at: datetime | None = None
    updated_at: datetime


class SupplierOfferCandidateListResponse(BaseModel):
    items: list[SupplierOfferCandidateResponse]
    meta: Meta


class SupplierOfferMappingPutPayload(BaseModel):
    product_id: int = Field(ge=1)
    replace_existing: bool = False
    expected_mapping_id: int | None = Field(default=None, ge=1)
    expected_product_id: int | None = Field(default=None, ge=1)


class SupplierOfferMappingResponse(BaseModel):
    offer_id: int
    id: int
    product_id: int
    supplier_id: int
    external_id: str
    is_active: bool
    mapped_by: str | None = None
    mapped_at: datetime
