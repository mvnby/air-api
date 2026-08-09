from datetime import datetime
from typing import Any, List, Optional
from sqlalchemy import Column, Index, JSON, Text, UniqueConstraint
from sqlmodel import Field, Relationship, SQLModel


class Brand(SQLModel, table=True):
    __tablename__ = "brand"

    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    logo_url: Optional[str] = Field(default=None)
    short_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    is_published: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)

    products: List["Product"] = Relationship(back_populates="brand")
    series: List["ProductSeries"] = Relationship(back_populates="brand")
    feature_links: List["FeatureBrandLink"] = Relationship(back_populates="brand")

    def __str__(self) -> str:
        return self.title


class ProductSeries(SQLModel, table=True):
    __tablename__ = "product_series"
    __table_args__ = (
        UniqueConstraint("brand_id", "slug", name="uq_product_series_brand_id_slug"),
        Index(
            "ix_product_series_brand_featured_public_sort",
            "brand_id",
            "is_featured",
            "is_published",
            "sort_order",
            "id",
        ),
    )

    id: Optional[int] = Field(default=None, primary_key=True)
    brand_id: Optional[int] = Field(
        default=None,
        foreign_key="brand.id",
        ondelete="SET NULL",
        index=True,
    )
    title: str = Field(index=True)
    slug: str = Field(index=True)
    tagline: Optional[str] = Field(default=None)
    short_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    hero_image: Optional[str] = Field(default=None)
    gallery_images: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    features: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    feature_blocks: List[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    content_blocks: List[dict[str, Any]] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    footnotes: List[str] = Field(
        default_factory=list,
        sa_column=Column(JSON, nullable=False),
    )
    seo_title: Optional[str] = Field(default=None)
    seo_description: Optional[str] = Field(default=None, sa_column=Column(Text))
    source_url: Optional[str] = Field(default=None)
    is_featured: bool = Field(default=False)
    is_published: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)

    brand: Optional[Brand] = Relationship(back_populates="series")
    products: List["Product"] = Relationship(back_populates="series")
    feature_links: List["FeatureSeriesLink"] = Relationship(back_populates="series")

    def __str__(self) -> str:
        return self.title
