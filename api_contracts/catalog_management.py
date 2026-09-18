"""Bounded requests for the editable catalog (including drafts)."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class CatalogManagementFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    search: str | None = Field(default=None, max_length=200)
    brand_ids: list[int] = Field(default_factory=list, max_length=100)
    series_ids: list[int] = Field(default_factory=list, max_length=100)
    supplier_id: int | None = Field(default=None, gt=0)
    category: Literal["household", "multi", "semi_industrial"] | None = None
    category_missing: bool = False
    cooling_btu_classes: list[Literal[7, 9, 12, 18, 24, 30, 36, 42, 60]] = Field(default_factory=list, max_length=9)
    cooling_min_kw: float | None = Field(default=None, ge=0)
    cooling_max_kw: float | None = Field(default=None, ge=0)
    retail_min_byn: float | None = Field(default=None, ge=0)
    retail_max_byn: float | None = Field(default=None, ge=0)
    area_min: float | None = Field(default=None, ge=0)
    area_max: float | None = Field(default=None, ge=0)
    indoor_form_factor: Literal["wall", "cassette", "duct", "floor_ceiling", "column", "console"] | None = None
    heating_min: Literal[-20, -25, -30] | None = None
    is_inverter: bool | None = None
    wifi: Literal["builtin", "ready", "none"] | None = None
    availability: Literal["in_stock", "out_of_stock"] | None = None
    is_published: bool | None = None
    missing: Literal["brand", "series", "image", "price"] | None = None
    feature_id: int | None = Field(default=None, gt=0)
    has_feature: bool | None = None
    in_yandex_feed: bool | None = None

    @model_validator(mode="after")
    def valid_ranges(self):
        for lower, upper in ((self.area_min, self.area_max), (self.cooling_min_kw, self.cooling_max_kw), (self.retail_min_byn, self.retail_max_byn)):
            if lower is not None and upper is not None and lower > upper:
                raise ValueError("Минимум не может быть больше максимума")
        if (self.feature_id is None) != (self.has_feature is None):
            raise ValueError("Укажите особенность и состояние её наличия вместе")
        return self


class CatalogManagementQuery(BaseModel):
    filters: CatalogManagementFilters = Field(default_factory=CatalogManagementFilters)
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=40, ge=1, le=100)
    sort: Literal["recommended", "newest", "price_asc", "price_desc", "title"] = "recommended"


class CatalogManagementSelection(BaseModel):
    product_ids: list[int]
    total: int
