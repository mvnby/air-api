from typing import Literal

from pydantic import BaseModel, Field


class YandexBusinessFeedSettingsPayload(BaseModel):
    selection_mode: Literal["all_published", "curated_collections"] = "all_published"
    include_services: bool = True
    require_ready_image: bool = False
    require_in_stock: bool = False


class YandexBusinessFeedSettingsResponse(YandexBusinessFeedSettingsPayload):
    pass


class YandexBusinessFeedProductExclusion(BaseModel):
    product_id: int
    product_title: str
    reason: str


class YandexBusinessEditorialCategoryQuality(BaseModel):
    category_id: int
    title: str
    offer_count: int = Field(ge=0)
    picture_count: int = Field(ge=0)


class YandexBusinessProductImageIssue(BaseModel):
    product_id: int
    product_title: str
    reason: str
    error: str | None = None


class YandexBusinessCollectionConflict(BaseModel):
    product_id: int
    product_title: str
    selected_collection_id: int
    selected_collection_title: str
    skipped_collection_id: int
    skipped_collection_title: str


class YandexBusinessFeedQualityReport(BaseModel):
    product_offer_count: int = Field(ge=0)
    product_picture_count: int = Field(ge=0)
    service_offer_count: int = Field(ge=0)
    editorial_categories: list[YandexBusinessEditorialCategoryQuality] = Field(
        default_factory=list
    )
    categories_below_minimum_pictures: list[
        YandexBusinessEditorialCategoryQuality
    ] = Field(default_factory=list)
    products_without_picture: list[YandexBusinessProductImageIssue] = Field(
        default_factory=list
    )
    image_generation_errors: list[YandexBusinessProductImageIssue] = Field(
        default_factory=list
    )
    collection_conflicts: list[YandexBusinessCollectionConflict] = Field(
        default_factory=list
    )
    excluded_product_count: int = Field(default=0, ge=0)
    excluded_products: list[YandexBusinessFeedProductExclusion] = Field(
        default_factory=list
    )


class YandexBusinessFeedPreview(YandexBusinessFeedQualityReport):
    settings: YandexBusinessFeedSettingsResponse
