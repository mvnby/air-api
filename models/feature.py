from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import CheckConstraint, Column, Index, JSON, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


FEATURE_SCOPE_TYPES = ("universal", "brand", "series", "product", "derived")
FEATURE_LINK_SOURCES = ("manual", "inherited", "derived")
FEATURE_RULE_OPERATORS = ("eq", "neq", "gt", "gte", "lt", "lte", "in", "contains", "exists")


class FeatureCategory(SQLModel, table=True):
    __tablename__ = "feature_category"

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    name: str = Field(index=True)
    sort_order: int = Field(default=0, index=True)
    is_active: bool = Field(default=True, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    features: List["Feature"] = Relationship(back_populates="category")


class Feature(SQLModel, table=True):
    __tablename__ = "feature"
    __table_args__ = (
        CheckConstraint(
            "scope_type IN ('universal', 'brand', 'series', 'product', 'derived')",
            name="ck_feature_scope_type",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    slug: str = Field(unique=True, index=True)
    name: str = Field(index=True)
    short_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    full_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    category_id: int = Field(foreign_key="feature_category.id", index=True)
    scope_type: str = Field(default="universal", index=True)
    brand_id: Optional[int] = Field(default=None, foreign_key="brand.id", ondelete="SET NULL", index=True)
    replaces_feature_id: Optional[int] = Field(
        default=None,
        foreign_key="feature.id",
        ondelete="SET NULL",
        index=True,
    )
    icon_media_id: Optional[int] = Field(default=None, foreign_key="media_asset.id", ondelete="SET NULL")
    image_media_id: Optional[int] = Field(default=None, foreign_key="media_asset.id", ondelete="SET NULL")
    icon: Optional[str] = None
    image_url: Optional[str] = None
    video_url: Optional[str] = None
    footnote: Optional[str] = None
    source_url: Optional[str] = None
    aliases: List[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    seo_title: Optional[str] = None
    seo_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    source_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    legal_notes: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    archived_at: Optional[datetime] = Field(default=None, index=True)

    category: Optional[FeatureCategory] = Relationship(back_populates="features")
    rules: List["FeatureRule"] = Relationship(back_populates="feature")
    brand_links: List["FeatureBrandLink"] = Relationship(back_populates="feature")
    series_links: List["FeatureSeriesLink"] = Relationship(back_populates="feature")
    product_links: List["FeatureProductLink"] = Relationship(back_populates="feature")


class FeatureRule(SQLModel, table=True):
    __tablename__ = "feature_rule"
    __table_args__ = (
        CheckConstraint(
            "operator IN ('eq', 'neq', 'gt', 'gte', 'lt', 'lte', 'in', 'contains', 'exists')",
            name="ck_feature_rule_operator",
        ),
        UniqueConstraint("feature_id", "spec_key", "operator", name="uq_feature_rule_definition"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    feature_id: int = Field(foreign_key="feature.id", ondelete="CASCADE", index=True)
    spec_key: str = Field(index=True)
    operator: str = Field(index=True)
    target_value: Any = Field(default=None, sa_column=Column(JSON, nullable=True))
    is_active: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)

    feature: Optional[Feature] = Relationship(back_populates="rules")


class FeatureLinkFields(SQLModel):
    source: str = Field(default="manual", index=True)
    is_enabled: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)
    override_title: Optional[str] = None
    override_description: Optional[str] = Field(default=None, sa_type=Text)
    override_media_id: Optional[int] = Field(default=None, foreign_key="media_asset.id", ondelete="SET NULL")
    override_image_url: Optional[str] = None
    override_icon: Optional[str] = None
    override_footnote: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)


class FeatureBrandLink(FeatureLinkFields, table=True):
    __tablename__ = "feature_brand_link"
    __table_args__ = (
        UniqueConstraint("brand_id", "feature_id", name="uq_feature_brand_link"),
        CheckConstraint(
            "source IN ('manual', 'inherited', 'derived')",
            name="ck_feature_brand_link_source",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    brand_id: int = Field(foreign_key="brand.id", ondelete="CASCADE", index=True)
    feature_id: int = Field(foreign_key="feature.id", ondelete="CASCADE", index=True)

    brand: Optional["Brand"] = Relationship(back_populates="feature_links")
    feature: Optional[Feature] = Relationship(back_populates="brand_links")


class FeatureSeriesLink(FeatureLinkFields, table=True):
    __tablename__ = "feature_series_link"
    __table_args__ = (
        UniqueConstraint("series_id", "feature_id", name="uq_feature_series_link"),
        CheckConstraint(
            "source IN ('manual', 'inherited', 'derived')",
            name="ck_feature_series_link_source",
        ),
        Index(
            "ix_feature_series_link_series_featured_sort",
            "series_id",
            "is_featured",
            "sort_order",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    series_id: int = Field(foreign_key="product_series.id", ondelete="CASCADE", index=True)
    feature_id: int = Field(foreign_key="feature.id", ondelete="CASCADE", index=True)
    is_featured: bool = Field(default=False, index=True)

    series: Optional["ProductSeries"] = Relationship(back_populates="feature_links")
    feature: Optional[Feature] = Relationship(back_populates="series_links")


class FeatureProductLink(FeatureLinkFields, table=True):
    __tablename__ = "feature_product_link"
    __table_args__ = (
        UniqueConstraint("product_id", "feature_id", name="uq_feature_product_link"),
        CheckConstraint(
            "source IN ('manual', 'inherited', 'derived')",
            name="ck_feature_product_link_source",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", ondelete="CASCADE", index=True)
    feature_id: int = Field(foreign_key="feature.id", ondelete="CASCADE", index=True)

    product: Optional["Product"] = Relationship(back_populates="feature_links")
    feature: Optional[Feature] = Relationship(back_populates="product_links")


# Expand-contract compatibility tables. They are read only in this release and
# remain in metadata until the previous blue-green image is no longer a rollback target.
class LegacyBrandFeature(SQLModel, table=True):
    __tablename__ = "brand_feature"
    __table_args__ = (
        UniqueConstraint("brand_id", "slug", name="uq_brand_feature_brand_id_slug"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    brand_id: int = Field(foreign_key="brand.id", index=True)
    title: str = Field(index=True)
    slug: str = Field(index=True)
    text: Optional[str] = Field(default=None, sa_column=Column(Text))
    image_url: Optional[str] = None
    icon: Optional[str] = None
    footnote: Optional[str] = None
    source_url: Optional[str] = None
    aliases: List[str] = Field(default_factory=list, sa_column=Column(JSON, nullable=False))
    is_published: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )


class LegacyProductSeriesFeatureLink(SQLModel, table=True):
    __tablename__ = "product_series_feature_link"
    __table_args__ = (
        UniqueConstraint("series_id", "feature_id", name="uq_product_series_feature_link"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    series_id: int = Field(foreign_key="product_series.id", index=True)
    feature_id: int = Field(foreign_key="brand_feature.id", index=True)
    sort_order: int = Field(default=0, index=True)
    title_override: Optional[str] = None
    text_override: Optional[str] = Field(default=None, sa_column=Column(Text))
    image_url_override: Optional[str] = None
    icon_override: Optional[str] = None
    footnote_override: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)
