"""Shared multi-split selection input with separate public/Manager projections."""

from typing import Literal

from pydantic import BaseModel, Field

from schemas_common import Meta


CompatibilityStatus = Literal["confirmed", "requires_specialist", "incompatible"]
MultiSplitKind = Literal["outdoor_unit", "indoor_unit"]


class MultiSplitRoomInput(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    indoor_product_id: int = Field(gt=0)
    area_m2: float | None = Field(default=None, gt=0, le=1000)
    required_cooling_kw: float | None = Field(default=None, gt=0, le=100)
    preferred_form: Literal["wall", "cassette", "duct", "floor_ceiling", "column", "console"] | None = None


class MultiSplitPreviewRequest(BaseModel):
    outdoor_product_id: int = Field(gt=0)
    rooms: list[MultiSplitRoomInput] = Field(min_length=1, max_length=8)


class MultiSplitOption(BaseModel):
    id: int
    title: str
    slug: str
    product_kind: MultiSplitKind
    price_byn: int
    cooling_power_kw: float | None = None
    indoor_form_factor: str | None = None
    availability: str


class MultiSplitOptionsResponse(BaseModel):
    items: list[MultiSplitOption]
    meta: Meta


class MultiSplitComponent(BaseModel):
    product_id: int
    title: str
    product_kind: str
    quantity: int
    unit_price_byn: int
    total_price_byn: int
    availability: str


class MultiSplitPreviewResponse(BaseModel):
    status: CompatibilityStatus
    explanation: str
    composition_complete: bool
    equipment_total_byn: int
    installation_total_byn: None = None
    components: list[MultiSplitComponent]
    source_url: str | None = None
    source_version: str | None = None


class ManagerMultiSplitPreviewResponse(MultiSplitPreviewResponse):
    purchase_cost_total_byn: float | None = None
    margin_byn: float | None = None


class MultiSplitLeadPayload(BaseModel):
    configuration: MultiSplitPreviewRequest
    name: str = Field(min_length=1, max_length=160)
    phone: str = Field(min_length=7, max_length=40)
    email: str | None = Field(default=None, max_length=254)
    message: str | None = Field(default=None, max_length=1000)
    consent: Literal[True]


class MultiSplitLeadResponse(BaseModel):
    lead_id: int
    status: str


class ManagerMultiSplitSavePayload(MultiSplitPreviewRequest):
    proposal_id: int | None = Field(default=None, gt=0)
    expected_status: CompatibilityStatus
    expected_components: list[MultiSplitComponent] = Field(min_length=2)
