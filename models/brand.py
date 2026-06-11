from datetime import datetime
from typing import List, Optional

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
    description: Optional[str] = Field(default=None, sa_column=Column(Text))
    hero_image: Optional[str] = Field(default=None)
    features: List[str] = Field(default=[], sa_column=Column(JSON))
    is_published: bool = Field(default=True, index=True)
    sort_order: int = Field(default=0)
    created_at: datetime = Field(default_factory=datetime.now)

    brand: Optional[Brand] = Relationship(back_populates="series")
    products: List["Product"] = Relationship(back_populates="series")

    def __str__(self) -> str:
        return self.title
