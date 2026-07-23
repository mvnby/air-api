from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from schemas import ProductKind, ProductResponse


CollectionStatus = Literal["draft", "published", "archived"]
CollectionMode = Literal["manual"]
class ProductCollectionFields(BaseModel):
    internal_name: str = Field(min_length=1, max_length=180)
    public_title: str = Field(min_length=1, max_length=180)
    public_description: str | None = None
    public_badge: str | None = Field(default=None, max_length=80)
    cta_label: str | None = Field(default=None, max_length=80)
    cta_url: str | None = Field(default=None, max_length=500)
    editorial_note: str | None = None
    status: CollectionStatus = "draft"
    mode: CollectionMode = "manual"
    min_items: int = Field(default=1, ge=1, le=24)
    max_items: int = Field(default=6, ge=1, le=24)
    fallback_collection_id: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def validate_limits_and_schedule(self):
        if self.max_items < self.min_items:
            raise ValueError("max_items must be greater than or equal to min_items")
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class ManagerProductCollectionCreate(ProductCollectionFields):
    slug: str | None = Field(default=None, max_length=120)


class ManagerProductCollectionUpdate(BaseModel):
    slug: str | None = Field(default=None, max_length=120)
    internal_name: str | None = Field(default=None, min_length=1, max_length=180)
    public_title: str | None = Field(default=None, min_length=1, max_length=180)
    public_description: str | None = None
    public_badge: str | None = Field(default=None, max_length=80)
    cta_label: str | None = Field(default=None, max_length=80)
    cta_url: str | None = Field(default=None, max_length=500)
    editorial_note: str | None = None
    status: CollectionStatus | None = None
    mode: CollectionMode | None = None
    min_items: int | None = Field(default=None, ge=1, le=24)
    max_items: int | None = Field(default=None, ge=1, le=24)
    fallback_collection_id: int | None = None
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class ManagerProductCollectionItemPayload(BaseModel):
    product_id: int
    is_pinned: bool = True
    editorial_note: str | None = None


class ManagerProductCollectionItemsPayload(BaseModel):
    items: list[ManagerProductCollectionItemPayload] = Field(default_factory=list, max_length=24)


class ManagerProductCollectionPlacementPayload(BaseModel):
    surface_key: str = Field(min_length=1, max_length=80)
    slot_key: str = Field(min_length=1, max_length=80)
    position: int = Field(default=0, ge=0)
    is_enabled: bool = True
    starts_at: datetime | None = None
    ends_at: datetime | None = None

    @model_validator(mode="after")
    def validate_schedule(self):
        if self.starts_at and self.ends_at and self.ends_at <= self.starts_at:
            raise ValueError("ends_at must be later than starts_at")
        return self


class ManagerProductCollectionPlacementsPayload(BaseModel):
    placements: list[ManagerProductCollectionPlacementPayload] = Field(default_factory=list, max_length=20)


class ManagerProductCollectionItemResponse(BaseModel):
    id: int
    product_id: int
    position: int
    is_pinned: bool
    editorial_note: str | None = None
    product_title: str
    product_slug: str
    product_kind: ProductKind
    is_published: bool
    price: int
    main_image: str | None = None


class ManagerProductCollectionPlacementResponse(BaseModel):
    id: int
    surface_key: str
    slot_key: str
    position: int
    is_enabled: bool
    starts_at: datetime | None = None
    ends_at: datetime | None = None


class ManagerProductCollectionResponse(ProductCollectionFields):
    id: int
    slug: str
    created_at: datetime
    updated_at: datetime
    items: list[ManagerProductCollectionItemResponse] = Field(default_factory=list)
    placements: list[ManagerProductCollectionPlacementResponse] = Field(default_factory=list)


class ManagerProductCollectionListResponse(BaseModel):
    items: list[ManagerProductCollectionResponse] = Field(default_factory=list)


class ProductCollectionExclusionResponse(BaseModel):
    product_id: int
    product_title: str
    position: int
    reason_codes: list[str]
    reasons: list[str]


class PublicProductCollectionItemResponse(BaseModel):
    selection_source: Literal["manual", "fallback"] = "manual"
    position: int
    product: ProductResponse


class ProductCollectionPreviewResponse(BaseModel):
    collection_id: int
    collection_slug: str
    below_min_items: bool
    fallback_used: bool = False
    items: list[PublicProductCollectionItemResponse] = Field(default_factory=list)
    excluded_items: list[ProductCollectionExclusionResponse] = Field(default_factory=list)


class PublicProductCollectionResponse(BaseModel):
    slug: str
    title: str
    description: str | None = None
    badge: str | None = None
    cta_label: str | None = None
    cta_url: str | None = None
    position: int
    updated_at: datetime
    items: list[PublicProductCollectionItemResponse] = Field(default_factory=list)


class PublicProductCollectionPlacementResponse(BaseModel):
    surface: str
    slot: str
    collections: list[PublicProductCollectionResponse] = Field(default_factory=list)
