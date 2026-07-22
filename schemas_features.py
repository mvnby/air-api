from datetime import datetime
from typing import Any, List, Literal, Optional

from pydantic import BaseModel, Field, field_validator, model_validator


FeatureScopeType = Literal["universal", "brand", "series", "product", "derived"]
FeatureRuleOperator = Literal["eq", "neq", "gt", "gte", "lt", "lte", "in", "contains", "exists"]
FeatureLinkSource = Literal["manual", "inherited", "derived"]
ResolvedFeatureSource = Literal["product_override", "product_manual", "series", "brand", "derived"]


class FeatureCategoryResponse(BaseModel):
    id: int
    slug: str
    name: str
    sort_order: int = 0
    is_active: bool = True


class FeatureRulePayload(BaseModel):
    spec_key: str = Field(min_length=1, max_length=120)
    operator: FeatureRuleOperator
    target_value: Any = None
    is_active: bool = True
    sort_order: int = 0

    @field_validator("spec_key")
    @classmethod
    def normalize_spec_key(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized or any(part in {"", "__class__", "__dict__"} for part in normalized.split(".")):
            raise ValueError("Invalid spec key")
        return normalized

    @model_validator(mode="after")
    def validate_target(self):
        if self.operator != "exists" and self.target_value is None:
            raise ValueError("target_value is required for this operator")
        if self.operator == "in" and not isinstance(self.target_value, list):
            raise ValueError("target_value must be a list for the in operator")
        return self


class FeatureRuleResponse(FeatureRulePayload):
    id: int
    feature_id: int


class FeatureCreatePayload(BaseModel):
    slug: Optional[str] = Field(default=None, max_length=160)
    name: str = Field(min_length=1, max_length=200)
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    category_id: int
    scope_type: FeatureScopeType = "universal"
    brand_id: Optional[int] = None
    icon_media_id: Optional[int] = None
    image_media_id: Optional[int] = None
    icon: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    footnote: Optional[str] = None
    source_url: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    source_notes: Optional[str] = None
    legal_notes: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0
    rules: List[FeatureRulePayload] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_scope(self):
        if self.scope_type == "brand" and self.brand_id is None:
            raise ValueError("brand_id is required for brand-scoped features")
        return self


class FeatureUpdatePayload(BaseModel):
    slug: Optional[str] = Field(default=None, max_length=160)
    name: Optional[str] = Field(default=None, min_length=1, max_length=200)
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    category_id: Optional[int] = None
    scope_type: Optional[FeatureScopeType] = None
    brand_id: Optional[int] = None
    icon_media_id: Optional[int] = None
    image_media_id: Optional[int] = None
    icon: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    footnote: Optional[str] = None
    source_url: Optional[str] = None
    aliases: Optional[List[str]] = None
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    source_notes: Optional[str] = None
    legal_notes: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    rules: Optional[List[FeatureRulePayload]] = None

    @model_validator(mode="after")
    def validate_required_updates(self):
        for field_name in ("name", "category_id", "scope_type", "is_active", "sort_order"):
            if field_name in self.model_fields_set and getattr(self, field_name) is None:
                raise ValueError(f"{field_name} cannot be null")
        return self


class PublicFeatureResponse(BaseModel):
    id: int
    slug: str
    name: str
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    category: FeatureCategoryResponse
    scope_type: FeatureScopeType
    source: ResolvedFeatureSource
    is_overridden: bool = False
    sort_order: int = 0
    feature_sort_order: int = 0
    icon: Optional[str] = None
    icon_url: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    footnote: Optional[str] = None
    applied_rule: Optional[str] = None


class ManagerFeatureResponse(BaseModel):
    id: int
    slug: str
    name: str
    short_description: Optional[str] = None
    full_description: Optional[str] = None
    category: FeatureCategoryResponse
    scope_type: FeatureScopeType
    brand_id: Optional[int] = None
    icon_media_id: Optional[int] = None
    image_media_id: Optional[int] = None
    icon: Optional[str] = None
    icon_url: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    footnote: Optional[str] = None
    source_url: Optional[str] = None
    aliases: List[str] = Field(default_factory=list)
    seo_title: Optional[str] = None
    seo_description: Optional[str] = None
    source_notes: Optional[str] = None
    legal_notes: Optional[str] = None
    is_active: bool
    sort_order: int
    rules: List[FeatureRuleResponse] = Field(default_factory=list)
    brands_count: int = 0
    series_count: int = 0
    products_count: int = 0
    created_at: datetime
    updated_at: datetime
    archived_at: Optional[datetime] = None


class ManagerFeatureListResponse(BaseModel):
    items: List[ManagerFeatureResponse]
    total: int


class FeatureLinkPayload(BaseModel):
    feature_id: int
    source: FeatureLinkSource = "manual"
    is_enabled: bool = True
    sort_order: int = 0
    override_title: Optional[str] = None
    override_description: Optional[str] = None
    override_media_id: Optional[int] = None
    override_image_url: Optional[str] = None
    override_icon: Optional[str] = None
    override_footnote: Optional[str] = None


class FeatureTargetLinkPayload(BaseModel):
    is_enabled: bool = True
    sort_order: int = 0
    override_title: Optional[str] = None
    override_description: Optional[str] = None
    override_media_id: Optional[int] = None
    override_image_url: Optional[str] = None
    override_icon: Optional[str] = None
    override_footnote: Optional[str] = None


class ManagerProductFeatureWorkspaceResponse(BaseModel):
    effective: List[PublicFeatureResponse] = Field(default_factory=list)
    automatic_suggestions: List[PublicFeatureResponse] = Field(default_factory=list)
    inherited: List[PublicFeatureResponse] = Field(default_factory=list)
    manual: List[PublicFeatureResponse] = Field(default_factory=list)
    manual_assignments: List[FeatureLinkPayload] = Field(default_factory=list)
    disabled_feature_ids: List[int] = Field(default_factory=list)


class ManagerProductFeaturesUpdatePayload(BaseModel):
    assignments: List[FeatureLinkPayload] = Field(default_factory=list)


class ManagerFeatureSuggestionsApplyPayload(BaseModel):
    feature_ids: List[int] = Field(default_factory=list)
