from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import Column, JSON, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class Brand(SQLModel, table=True):
    __tablename__ = "brand"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    logo_url: Optional[str] = Field(default=None)
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_published: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)

    products: List["Product"] = Relationship(back_populates="brand")
    series: List["ProductSeries"] = Relationship(back_populates="brand")
    feature_library: List["BrandFeature"] = Relationship(back_populates="brand")

    def __str__(self) -> str:
        return self.title


class ProductSeries(SQLModel, table=True):
    __tablename__ = "product_series"
    __table_args__ = (
        UniqueConstraint("brand_id", "slug", name="uq_product_series_brand_id_slug"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    brand_id: Optional[int] = Field(default=None, foreign_key="brand.id", index=True)
    title: str = Field(index=True)
    slug: str = Field(index=True)
    tagline: Optional[str] = Field(default=None)
    short_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    hero_image: Optional[str] = Field(default=None)
    gallery_images: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    features: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    feature_blocks: List[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    content_blocks: List[dict[str, Any]] = Field(default_factory=list, sa_column=Column(JSON))
    footnotes: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    seo_title: Optional[str] = Field(default=None)
    seo_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    source_url: Optional[str] = Field(default=None)
    is_published: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)

    brand: Optional[Brand] = Relationship(back_populates="series")
    products: List["Product"] = Relationship(back_populates="series")
    feature_links: List["ProductSeriesFeatureLink"] = Relationship(back_populates="series")

    def __str__(self) -> str:
        return self.title


class BrandFeature(SQLModel, table=True):
    __tablename__ = "brand_feature"
    __table_args__ = (
        UniqueConstraint("brand_id", "slug", name="uq_brand_feature_brand_id_slug"),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    brand_id: int = Field(foreign_key="brand.id", index=True)
    title: str = Field(index=True)
    slug: str = Field(index=True)
    text: Optional[str] = Field(default=None, sa_column=Column(Text))
    image_url: Optional[str] = Field(default=None)
    icon: Optional[str] = Field(default=None)
    footnote: Optional[str] = Field(default=None)
    source_url: Optional[str] = Field(default=None)
    aliases: List[str] = Field(default_factory=list, sa_column=Column(JSON))
    is_published: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0, index=True)
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(
        default_factory=datetime.now,
        sa_column_kwargs={"onupdate": datetime.now},
    )

    brand: Optional[Brand] = Relationship(back_populates="feature_library")
    series_links: List["ProductSeriesFeatureLink"] = Relationship(back_populates="feature")

    def __str__(self) -> str:
        return self.title


class ProductSeriesFeatureLink(SQLModel, table=True):
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

    series: Optional[ProductSeries] = Relationship(back_populates="feature_links")
    feature: Optional[BrandFeature] = Relationship(back_populates="series_links")
