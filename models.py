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
    color: str = Field(default="secondary") # Bootstrap classes: primary, success, info, warning, danger, secondary
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
    is_inverter: bool = Field(default=False, index=True)
    power_cooling: Optional[float] = Field(default=None, index=True)
    
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
    source_url: Optional[str] = Field(default=None, index=True)

    # Virtual field for admin file upload (not in DB)
    @property
    def main_image_file(self) -> Any:
        return getattr(self, "_temp_main_image_file", None)
    
    @main_image_file.setter
    def main_image_file(self, value: Any):
        self._temp_main_image_file = value

    def __str__(self):
        return f"{self.title} ({self.price} р)"

class Article(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    slug: str = Field(unique=True, index=True)
    content: str
    main_image: Optional[str] = None
    is_published: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)

    # Virtual field for admin file upload
    @property
    def main_image_file(self) -> Any:
        return getattr(self, "_temp_main_image_file", None)
    
    @main_image_file.setter
    def main_image_file(self, value: Any):
        self._temp_main_image_file = value

    def __str__(self):
        return self.title

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int # Telegram User ID
    username: Optional[str] = None
    full_name: Optional[str] = None
    phone: Optional[str] = None
    product_id: int = Field(foreign_key="product.id")
    status: str = Field(default="new") # new, in_progress, done, cancelled
    created_at: datetime = Field(default_factory=datetime.utcnow)
    
    product: Optional[Product] = Relationship()

    def __str__(self):
        return f"Заказ #{self.id} от {self.full_name or self.username}"
class Favorite(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int = Field(index=True) # Telegram User ID
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
