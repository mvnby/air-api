"""Closed installation price-book, resolver, and preview contracts."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
import re
from typing import Literal

from pydantic import BaseModel, Field, model_validator


IndoorType = Literal["wall", "cassette", "duct", "floor_ceiling", "column", "console"]
PriceMode = Literal["fixed", "from", "quote"]
ResolutionStatus = Literal["fixed", "from", "provisional", "quote", "unavailable"]
WorkKind = Literal["standard", "prelaid_route"]
WeightSource = Literal["weight_indoor", "weight_outdoor", "weight_indoor_package", "weight_outdoor_package"]


class InstallationMatcher(BaseModel):
    product_kind: Literal["complete_split_system", "multi_split_system"] = "complete_split_system"
    indoor_type: IndoorType | None = None
    work_kind: WorkKind = "standard"
    match_strategy: Literal["strict", "capacity_only", "type_only"] = "strict"
    capacity_min_kw: Decimal | None = Field(default=None, ge=0, le=1000, decimal_places=3)
    capacity_max_kw: Decimal | None = Field(default=None, gt=0, le=1000, decimal_places=3)
    capacity_min_inclusive: bool = True
    capacity_max_inclusive: bool = True
    pipe_liquid: str | None = None
    pipe_gas: str | None = None
    weight_source: WeightSource | None = None
    weight_min_kg: Decimal | None = Field(default=None, ge=0, le=10000, decimal_places=2)
    weight_max_kg: Decimal | None = Field(default=None, gt=0, le=10000, decimal_places=2)

    @model_validator(mode="after")
    def bounds(self):
        if self.capacity_min_kw is not None and self.capacity_max_kw is not None and self.capacity_min_kw >= self.capacity_max_kw:
            raise ValueError("capacity_min_kw must be less than capacity_max_kw")
        if self.product_kind == "complete_split_system" and self.indoor_type is None:
            raise ValueError("complete split matcher requires indoor_type")
        if self.product_kind == "multi_split_system" and self.indoor_type is not None:
            raise ValueError("multi split matcher describes the whole system, not one indoor type")
        if self.match_strategy in {"capacity_only", "type_only"} and (self.pipe_liquid is not None or self.pipe_gas is not None or self.weight_source is not None):
            raise ValueError("capacity/type matcher cannot depend on pipe or weight")
        if self.match_strategy == "type_only" and (self.capacity_min_kw is not None or self.capacity_max_kw is not None):
            raise ValueError("type_only matcher cannot depend on cooling capacity")
        if (self.pipe_liquid is None) != (self.pipe_gas is None):
            raise ValueError("pipe_liquid and pipe_gas must be supplied together")
        if (self.weight_min_kg is not None or self.weight_max_kg is not None) and self.weight_source is None:
            raise ValueError("weight_source is required for weight bounds")
        if self.weight_min_kg is not None and self.weight_max_kg is not None and self.weight_min_kg >= self.weight_max_kg:
            raise ValueError("weight_min_kg must be less than weight_max_kg")
        return self


class TypedInstallationProfile(BaseModel):
    product_kind: str
    indoor_type: IndoorType | None = None
    capacity_cooling_kw: Decimal | None = Field(default=None, gt=0, le=1000, decimal_places=3)
    indoor_unit_count: int | None = Field(default=None, ge=2, le=20)
    composition_note: str | None = Field(default=None, min_length=8, max_length=500)
    pipe_liquid: str | None = None
    pipe_gas: str | None = None
    weight_indoor: Decimal | None = Field(default=None, gt=0, le=10000, decimal_places=2)
    weight_outdoor: Decimal | None = Field(default=None, gt=0, le=10000, decimal_places=2)
    weight_indoor_package: Decimal | None = Field(default=None, gt=0, le=10000, decimal_places=2)
    weight_outdoor_package: Decimal | None = Field(default=None, gt=0, le=10000, decimal_places=2)
    confirmed: bool = False

    @model_validator(mode="after")
    def confirmed_composition(self):
        if self.product_kind == "multi_split_system":
            if self.indoor_type is not None:
                raise ValueError("multisplit profile describes the whole system, not one indoor type")
            if self.composition_note is not None and len(self.composition_note.strip()) < 8:
                raise ValueError("multisplit composition note must describe the confirmed system")
        elif self.indoor_unit_count is not None or self.composition_note is not None:
            raise ValueError("indoor unit count and composition note are only for multisplit systems")
        return self


class InstallationTarget(BaseModel):
    product_id: int | None = Field(default=None, ge=1)
    typed_profile: TypedInstallationProfile | None = None
    work_kind: WorkKind = "standard"

    @model_validator(mode="after")
    def exactly_one_source(self):
        if (self.product_id is None) == (self.typed_profile is None):
            raise ValueError("provide exactly one of product_id and typed_profile")
        return self


class InstallationResolvePayload(InstallationTarget):
    pass


class InstallationResolveResponse(BaseModel):
    status: ResolutionStatus
    reason_code: str | None = None
    profile: TypedInstallationProfile | None = None
    profile_sources: dict[str, str] = Field(default_factory=dict)
    matched_by: list[str] = Field(default_factory=list)
    tariff_code: str | None = None
    scope_ref: str
    price_book_id: int | None = None
    price_book_revision: int | None = None
    included: dict[str, object] = Field(default_factory=dict)
    available_extras: list[str] = Field(default_factory=list)
    explanation: str | None = None
    price_mode: PriceMode | None = None
    base_price: Decimal | None = None


class InstallationExtraInput(BaseModel):
    code: str = Field(min_length=1)
    quantity: Decimal = Field(default=Decimal("1"), gt=0, le=1000, decimal_places=2)


class InstallationSiteApproval(BaseModel):
    code: Literal["access.scaffold", "access.lift"]
    actual_total: Decimal = Field(ge=0, le=1000000, decimal_places=2)
    scope_note: str = Field(min_length=8, max_length=500)

    @model_validator(mode="after")
    def described_scope(self):
        if len(self.scope_note.strip()) < 8:
            raise ValueError("approved site access needs a meaningful scope note")
        return self


class InstallationInput(InstallationTarget):
    key: str = Field(min_length=1, max_length=80)
    display_label: str | None = Field(default=None, min_length=1, max_length=100)
    route_length_m: Decimal = Field(ge=0, le=1000, decimal_places=2)
    holes_by_type: dict[str, Decimal]
    extras: list[InstallationExtraInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def valid_holes(self):
        if any(re.fullmatch(r"[a-z][a-z0-9_]*", kind) is None or
               not value.is_finite() or value < 0 or value > 100 or value != value.to_integral_value()
               for kind, value in self.holes_by_type.items()):
            raise ValueError("holes_by_type keys must be stable codes and quantities whole between 0 and 100")
        return self


class InstallationPreviewPayload(BaseModel):
    installations: list[InstallationInput] = Field(min_length=1, max_length=20)
    site_extras: list[InstallationExtraInput] = Field(default_factory=list)
    approved_site_access: list[InstallationSiteApproval] = Field(default_factory=list)
    expected_revision: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def unique_keys(self):
        keys = [item.key for item in self.installations]
        if len(keys) != len(set(keys)):
            raise ValueError("installation keys must be unique")
        access_codes = [item.code for item in self.approved_site_access]
        if len(access_codes) != len(set(access_codes)) or any(code not in {item.code for item in self.site_extras} for code in access_codes):
            raise ValueError("site approvals must be unique and match selected site work")
        return self


class InstallationComponent(BaseModel):
    code: str
    installation_key: str | None = None
    unit: str
    quantity: Decimal
    unit_price: Decimal
    gross: Decimal
    discount: Decimal = Decimal("0.00")
    net: Decimal
    description: str
    actual: Decimal | None = None
    included: Decimal | None = None
    is_provisional: bool = False


class InstallationAppliedDiscount(BaseModel):
    code: str
    installation_key: str
    amount: Decimal


class InstallationMeasuredWork(BaseModel):
    code: str
    label: str
    unit: str
    actual: Decimal
    included: Decimal
    extra: Decimal


class InstallationSelectedWork(BaseModel):
    code: str
    label: str
    unit: str
    quantity: Decimal
    scope_note: str | None = None


class InstallationWorkSummary(BaseModel):
    installation_key: str
    display_label: str | None = None
    tariff_code: str
    work_label: str
    measured: list[InstallationMeasuredWork]
    selected_extras: list[InstallationSelectedWork]


class InstallationPreviewResponse(BaseModel):
    status: ResolutionStatus
    reason_code: str | None = None
    scope_ref: str
    currency: Literal["BYN"] = "BYN"
    components: list[InstallationComponent] = Field(default_factory=list)
    applied_discounts: list[InstallationAppliedDiscount] = Field(default_factory=list)
    installations: list[InstallationWorkSummary] = Field(default_factory=list)
    site_work: list[InstallationSelectedWork] = Field(default_factory=list)
    customer_text: str | None = None
    subtotal: Decimal | None = None
    discount: Decimal | None = None
    total: Decimal | None = None
    price_book_id: int | None = None
    price_book_revision: int | None = None
    preview_ref: str | None = None
    expires_at: datetime | None = None
    explanation: str | None = None


class InstallationPublishResponse(BaseModel):
    price_book_id: int
    revision: int
    fingerprint: str
    tariff_count: int
    published_at: datetime


class InstallationLegacyCandidate(BaseModel):
    tariff_code: str
    matcher: InstallationMatcher
    mode: PriceMode
    base_price: Decimal
    route_extra_price: Decimal | None = None


class InstallationLegacyComparisonRow(BaseModel):
    legacy_rate_id: int
    legacy_category: str
    legacy_power_range: str
    legacy_base_price: Decimal
    legacy_route_extra_price: Decimal
    candidates: list[InstallationLegacyCandidate] = Field(default_factory=list)
    status: Literal["price_equal_review_required", "price_diff_review_required", "unmapped_review_required"]


class InstallationLegacyComparisonResponse(BaseModel):
    price_book_revision: int | None = None
    items: list[InstallationLegacyComparisonRow]
