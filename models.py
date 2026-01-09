from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, JSON, Column, Relationship
from datetime import datetime

class ProductTagLink(SQLModel, table=True):
    # We keep the name 'ProductCategoryLink' distinct or rename it to 'ProductTagLink'
    # Current request implies full migration. Let's rename class to ProductTagLink
    __tablename__ = "product_tag_link"
    product_id: Optional[int] = Field(default=None, foreign_key="product.id", primary_key=True)
    tag_id: Optional[int] = Field(default=None, foreign_key="tag.id", primary_key=True)

class TagGroup(SQLModel, table=True):
    __tablename__ = "tag_group"
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    slug: str = Field(unique=True, index=True)
    is_public: bool = Field(default=True)
    sort_order: int = Field(default=0)
    allow_multiple: bool = Field(default=False)
    
    tags: List["Tag"] = Relationship(back_populates="group")

class Tag(SQLModel, table=True):
    __tablename__ = "tag"
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: Optional[int] = Field(default=None, foreign_key="tag_group.id")
    title: str = Field(index=True)
    slug: str = Field(index=True)
    # Additional fields
    is_public: bool = Field(default=True)
    is_filter: bool = Field(default=False)
    sort_order: int = Field(default=0)
    ai_snippet: Optional[str] = None
    reliability_score: Optional[float] = None
    
    group: Optional[TagGroup] = Relationship(back_populates="tags")
    products: List["Product"] = Relationship(back_populates="tags", link_model=ProductTagLink)
    
    def __str__(self):
        return self.title

class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    title: str = Field(index=True)
    description: str = Field(default="")
    
    price: int
    old_price: Optional[int] = None
    area: int = Field(default=0, index=True)
    
    # 1. Главная картинка
    main_image: Optional[str] = Field(default=None)
    
    # 2. Галерея
    images: List[str] = Field(default=[], sa_column=Column(JSON))
    
    # 3. Категории (Теперь связь M2M)
    # 3. Теги (Бывшие Категории)
    tags: List[Tag] = Relationship(back_populates="products", link_model=ProductTagLink)

    # 4. JSONSpecs
    specs: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    is_published: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)

class Article(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    content: str
    image_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)