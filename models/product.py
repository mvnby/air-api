from datetime import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import Column, String, UniqueConstraint
from sqlmodel import Field, JSON, Relationship, SQLModel


class ProductTagLink(SQLModel, table=True):
    __tablename__ = "product_tag_link"
    product_id: Optional[int] = Field(default=None, foreign_key="product.id", primary_key=True)
    tag_id: Optional[int] = Field(default=None, foreign_key="tag.id", primary_key=True)


class TagGroup(SQLModel, table=True):
    __tablename__ = "tag_group"
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    is_public: bool = Field(default=True)
    is_expert_badge: bool = Field(default=False, index=True)
    color: str = Field(default="secondary")
    sort_order: int = Field(default=0)
    allow_multiple: bool = Field(default=False)

    tags: List["Tag"] = Relationship(back_populates="group")

    def __str__(self):
        return self.title


class Tag(SQLModel, table=True):
    __tablename__ = "tag"
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: Optional[int] = Field(default=None, foreign_key="tag_group.id")
    title: str = Field(index=True)
    slug: str = Field(index=True, unique=True)
    is_public: bool = Field(default=True)
    is_filter: bool = Field(default=False)
    sort_order: int = Field(default=0)
    ai_snippet: Optional[str] = None
    reliability_score: Optional[float] = None

    group: Optional[TagGroup] = Relationship(back_populates="tags")
    products: List["Product"] = Relationship(back_populates="tags", link_model=ProductTagLink)

    def __str__(self):
        from sqlalchemy.orm.attributes import instance_state

        state = instance_state(self)
        if "group" in state.dict:
            group = state.dict["group"]
            if group:
                return f"[{group.title}] {self.title}"
        return self.title


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    title: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    description: str = Field(default="")

    price: int
    old_price: Optional[int] = None
    area: int = Field(default=0, index=True)
    is_inverter: bool = Field(default=False, index=True)
    power_cooling: Optional[float] = Field(default=None, index=True)

    main_image: Optional[str] = Field(default=None)
    images: List[str] = Field(default=[], sa_column=Column(JSON))
    gallery_images: List["ProductImage"] = Relationship(back_populates="product")

    tags: List[Tag] = Relationship(back_populates="products", link_model=ProductTagLink)
    order_links: List["OrderProductLink"] = Relationship(back_populates="product")

    specs: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))

    is_published: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)
    source_url: Optional[str] = Field(default=None, index=True)

    @property
    def main_image_file(self) -> Any:
        return getattr(self, "_temp_main_image_file", None)

    @main_image_file.setter
    def main_image_file(self, value: Any):
        self._temp_main_image_file = value

    def __str__(self):
        return f"{self.title} ({self.price} р)"


class ProductImage(SQLModel, table=True):
    __tablename__ = "product_image"
    __table_args__ = (
        UniqueConstraint("product_id", "url", name="uq_product_image_product_id_url"),
    )
    id: Optional[int] = Field(default=None, primary_key=True)
    product_id: int = Field(foreign_key="product.id", index=True)
    url: str
    is_installation_photo: bool = Field(default=False, index=True)
    created_at: datetime = Field(default_factory=datetime.now)

    product: "Product" = Relationship(back_populates="gallery_images")

    def __str__(self):
        photo_type = "Installation" if self.is_installation_photo else "Gallery"
        return f"{photo_type} photo for product #{self.product_id}"


class Article(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    slug: str = Field(unique=True, index=True)
    content: str
    main_image: Optional[str] = None
    cover_image: Optional[str] = None
    is_published: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)

    @property
    def main_image_file(self) -> Any:
        return getattr(self, "_temp_main_image_file", None)

    @main_image_file.setter
    def main_image_file(self, value: Any):
        self._temp_main_image_file = value

    @property
    def cover_image_file(self) -> Any:
        return getattr(self, "_temp_cover_image_file", None)

    @cover_image_file.setter
    def cover_image_file(self, value: Any):
        self._temp_cover_image_file = value

    def __str__(self):
        return self.title


class Favorite(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True)
    product_id: int = Field(foreign_key="product.id")
    created_at: datetime = Field(default_factory=datetime.now)

    product: Optional[Product] = Relationship()


class GlobalConfig(SQLModel, table=True):
    __tablename__ = "global_config"
    id: Optional[int] = Field(default=None, primary_key=True)
    key: str = Field(unique=True, index=True)
    value: str
    description: Optional[str] = None
    updated_at: datetime = Field(default_factory=datetime.now)

    def __str__(self):
        return f"{self.key}: {self.value}"


class InstallationRate(SQLModel, table=True):
    __tablename__ = "installation_rates"
    id: Optional[int] = Field(default=None, primary_key=True)

    category: str = Field(index=True)
    power_range: str = Field(default="")

    base_price: int = Field(default=0)
    extra_pipe_price: int = Field(default=0)
    included_pipe_meters: int = Field(default=3)

    is_fixed: bool = Field(default=True)

    comment: Optional[str] = Field(default=None, sa_column=Column(String))

    def __str__(self):
        return f"{self.category} {self.power_range} ({self.base_price}r)"
