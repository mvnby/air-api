"""Schemas shared by public product-series and Manager series workflows."""

from datetime import datetime
from typing import List, Literal, Optional

from pydantic import BaseModel, Field, PrivateAttr, model_serializer

from schemas_features import ManagerFeatureSeriesAssignmentPayload


class ProductSeriesFeatureBlockResponse(BaseModel):
    title: str
    text: Optional[str] = None
    image_url: Optional[str] = None
    icon: Optional[str] = None
    footnote: Optional[str] = None


class ProductSeriesBrandFeatureResponse(BaseModel):
    id: int
    title: str
    slug: str
    text: Optional[str] = None
    image_url: Optional[str] = None
    icon: Optional[str] = None
    footnote: Optional[str] = None
    source_url: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    is_published: bool = True
    sort_order: int = 0
    _disclose_source_url: bool = PrivateAttr(default=True)

    @model_serializer(mode="wrap")
    def _serialize_source_disclosure(self, handler):
        payload = handler(self)
        if not self._disclose_source_url:
            payload.pop("source_url", None)
        return payload


class ManagerSeriesCatalogFeatureResponse(ProductSeriesBrandFeatureResponse):
    is_featured: bool = False


class ProductSeriesContentBlockResponse(BaseModel):
    kind: Literal["text", "image_text", "media"] = "text"
    title: Optional[str] = None
    text: Optional[str] = None
    image_url: Optional[str] = None
    layout: Literal["text_left", "text_right", "full"] = "text_left"


class ManagerBrandSeriesResponse(BaseModel):
    id: int
    brand_id: Optional[int] = None
    title: str
    slug: str
    tagline: Optional[str] = None
    short_description: Optional[str] = None
    description: Optional[str] = None
    hero_image: Optional[str] = None
    gallery_images: List[str] = Field(default_factory=list)
    features: List[str] = Field(default_factory=list)
    brand_features: List[ProductSeriesBrandFeatureResponse] = Field(default_factory=list)
    brand_feature_ids: List[int] = Field(default_factory=list)
    feature_assignments: List[ManagerFeatureSeriesAssignmentPayload] = Field(default_factory=list)
    catalog_features: List[ManagerSeriesCatalogFeatureResponse] = Field(default_factory=list)
    feature_blocks: List[ProductSeriesFeatureBlockResponse] = Field(default_factory=list)
    content_blocks: List[ProductSeriesContentBlockResponse] = Field(default_factory=list)
    footnotes: List[str] = Field(default_factory=list)
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    source_url: Optional[str] = None
    is_featured: bool = False
    is_published: bool
    sort_order: int
    created_at: datetime
    products_count: int = 0


class ManagerBrandSeriesListResponse(BaseModel):
    items: List[ManagerBrandSeriesResponse]


class ManagerBrandSeriesCreatePayload(BaseModel):
    title: str
    slug: Optional[str] = None
    tagline: Optional[str] = None
    short_description: Optional[str] = None
    description: Optional[str] = None
    hero_image: Optional[str] = None
    gallery_images: List[str] = Field(default_factory=list)
    features: List[str] = Field(default_factory=list)
    brand_feature_ids: List[int] = Field(default_factory=list)
    feature_assignments: Optional[List[ManagerFeatureSeriesAssignmentPayload]] = None
    feature_blocks: List[ProductSeriesFeatureBlockResponse] = Field(default_factory=list)
    content_blocks: List[ProductSeriesContentBlockResponse] = Field(default_factory=list)
    footnotes: List[str] = Field(default_factory=list)
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    source_url: Optional[str] = None
    is_published: bool = True
    sort_order: int = 0


class ManagerBrandSeriesUpdatePayload(BaseModel):
    title: Optional[str] = None
    slug: Optional[str] = None
    tagline: Optional[str] = None
    short_description: Optional[str] = None
    description: Optional[str] = None
    hero_image: Optional[str] = None
    gallery_images: Optional[List[str]] = None
    features: Optional[List[str]] = None
    brand_feature_ids: Optional[List[int]] = None
    feature_assignments: Optional[List[ManagerFeatureSeriesAssignmentPayload]] = None
    feature_blocks: Optional[List[ProductSeriesFeatureBlockResponse]] = None
    content_blocks: Optional[List[ProductSeriesContentBlockResponse]] = None
    footnotes: Optional[List[str]] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    source_url: Optional[str] = None
    is_featured: Optional[bool] = None
    is_published: Optional[bool] = None
    sort_order: Optional[int] = None
