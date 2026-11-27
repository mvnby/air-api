"""Customer-facing product information for the authenticated staff Mini App."""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


PositiveId = Annotated[int, Field(gt=0)]
Nonnegative = Annotated[float, Field(ge=0, allow_inf_nan=False)]
CoolingClass = Literal[7, 9, 12, 18, 24, 30, 36, 42, 60]
Wifi = Literal["builtin", "ready", "none"]
ShopSort = Literal["recommended", "retail_price", "title", "cooling_power", "availability"]


class BotShopFilters(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    search: str | None = Field(default=None, max_length=200)
    brand_ids: list[PositiveId] = Field(default_factory=list, max_length=100)
    series_ids: list[PositiveId] = Field(default_factory=list, max_length=100)
    feature_ids: list[PositiveId] = Field(default_factory=list, max_length=100)
    cooling_btu_classes: list[CoolingClass] = Field(default_factory=list, max_length=9)
    cooling_min_kw: Nonnegative | None = None
    cooling_max_kw: Nonnegative | None = None
    area_min: Nonnegative | None = None
    area_max: Nonnegative | None = None
    retail_min_byn: Nonnegative | None = None
    retail_max_byn: Nonnegative | None = None
    is_inverter: bool | None = None
    wifi: Wifi | None = None
    availability: Literal["in_stock", "out_of_stock", "all"] = "in_stock"
    category: Literal["household", "semi_industrial"] | None = None
    indoor_form_factor: Literal["wall", "cassette", "duct", "floor_ceiling", "column", "console"] | None = None
    heating_min: Literal[-20, -25, -30] | None = None

    @model_validator(mode="after")
    def ordered_ranges(self):
        for lower, upper, label in (
            (self.cooling_min_kw, self.cooling_max_kw, "мощности"),
            (self.area_min, self.area_max, "площади"),
            (self.retail_min_byn, self.retail_max_byn, "цены"),
        ):
            if lower is not None and upper is not None and lower > upper:
                raise ValueError(f"Нижняя граница {label} превышает верхнюю")
        return self


class BotShopProductRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_id: PositiveId
    expected_context_version: int = Field(ge=0)


class BotShopFacetsRequest(BotShopProductRequest):
    filters: BotShopFilters = Field(default_factory=BotShopFilters)


class BotShopResolveRequest(BotShopProductRequest):
    product_ids: list[PositiveId] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_products(self):
        if len(self.product_ids) != len(set(self.product_ids)):
            raise ValueError("Идентификаторы товаров должны быть уникальны")
        return self


class BotShopBrowseRequest(BotShopFacetsRequest):
    page: int = Field(default=1, ge=1, le=1_000_000)
    limit: int = Field(default=20, ge=1, le=100)
    sort: ShopSort = "recommended"
    direction: Literal["asc", "desc"] = "asc"


class BotShopItem(BaseModel):
    id: PositiveId
    title: str
    brand_title: str | None
    series_title: str | None
    thumbnail_url: str | None
    retail_price_byn: float
    availability: Literal["in_stock", "out_of_stock"]
    cooling_power_kw: float | None
    area_m2: float | None
    is_inverter: bool
    wifi: Wifi
    public_site_url: str | None


class BotShopPage(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class BotShopBrowseResponse(BaseModel):
    items: list[BotShopItem]
    meta: BotShopPage


class BotShopResolveResponse(BaseModel):
    items: list[BotShopItem]


class BotShopFeature(BaseModel):
    id: PositiveId
    slug: str
    title: str
    category: str


class BotShopBrandFacet(BaseModel):
    id: PositiveId
    title: str
    count: int


class BotShopSeriesFacet(BotShopBrandFacet):
    brand_id: int | None


class BotShopCoolingFacet(BaseModel):
    value: CoolingClass
    count: int


class BotShopFeatureFacet(BotShopFeature):
    count: int


class BotShopFacetsResponse(BaseModel):
    total: int
    brands: list[BotShopBrandFacet]
    series: list[BotShopSeriesFacet]
    cooling_btu_classes: list[BotShopCoolingFacet]
    features: list[BotShopFeatureFacet]


class BotShopImage(BaseModel):
    url: str
    thumbnail_url: str
    alt: str


class BotShopSpecification(BaseModel):
    key: str
    label: str
    value: str
    unit: str | None


class BotShopSpecificationGroup(BaseModel):
    key: str
    label: str
    items: list[BotShopSpecification]


class BotShopProductResponse(BotShopItem):
    description: str
    images: list[BotShopImage]
    summary_fields: list[BotShopSpecification]
    specification_groups: list[BotShopSpecificationGroup]
    features: list[BotShopFeature]
