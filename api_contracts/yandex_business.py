from pydantic import BaseModel, Field


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
