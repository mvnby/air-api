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
    slug: str = Field(index=True, unique=True)
    # Additional fields
    is_public: bool = Field(default=True)
    is_filter: bool = Field(default=False)
    sort_order: int = Field(default=0)
    ai_snippet: Optional[str] = None
    reliability_score: Optional[float] = None
    
    group: Optional[TagGroup] = Relationship(back_populates="tags")
    products: List["Product"] = Relationship(back_populates="tags", link_model=ProductTagLink)
    
    def __str__(self):
        # Safe access to group to avoid lazy load errors in async context
        # Use sqlalchemy.orm.attributes.instance_state to check if group is loaded
        from sqlalchemy.orm.attributes import instance_state
        state = instance_state(self)
        if 'group' in state.dict:
            group = state.dict['group']
            if group:
                return f"[{group.title}] {self.title}"
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
    order_links: List["OrderProductLink"] = Relationship(back_populates="product")

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

# --- CUSTOMERS (ФАЗА 24) ---

from enum import Enum

class CustomerType(str, Enum):
    individual = "individual"
    company = "company"

class Customer(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Core
    name: str = Field(index=True)  # Short display name
    phone: str = Field(index=True)
    email: Optional[str] = None
    type: CustomerType = Field(default=CustomerType.individual)
    
    # Legal (Company)
    full_legal_name: Optional[str] = None  # Полное наименование
    inn: Optional[str] = Field(default=None, index=True)  # ИНН/УНП
    kpp: Optional[str] = None  # КПП
    legal_address: Optional[str] = None  # Юридический адрес
    actual_address: Optional[str] = None  # Фактический/почтовый адрес
    
    # Bank
    bank_name: Optional[str] = None
    bic: Optional[str] = None
    iban: Optional[str] = None  # Расчетный счет
    
    # Signatory (for contracts)
    signer_position: str = Field(default="Генерального директора")  # В лице...
    signer_name: Optional[str] = None  # ФИО подписанта
    acting_basis: str = Field(default="Устава")  # Действующего на основании...
    
    created_at: datetime = Field(default_factory=datetime.now)
    
    # Relationships
    orders: List["Order"] = Relationship(back_populates="customer")

    def __str__(self):
        return self.name
        
# --- SHOPPING CART (PHASE 27) ---

class Cart(SQLModel, table=True):
    user_id: int = Field(primary_key=True) # Telegram User ID
    created_at: datetime = Field(default_factory=datetime.now)
    # Используем cascade delete, чтобы при удалении корзины удалялись товары
    items: List["CartItem"] = Relationship(
        back_populates="cart", 
        sa_relationship_kwargs={
            "lazy": "selectin", 
            "cascade": "all, delete-orphan"
        }
    )

class CartItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    cart_user_id: int = Field(foreign_key="cart.user_id")
    product_id: int = Field(foreign_key="product.id")
    quantity: int = Field(default=1)
    
    cart: "Cart" = Relationship(back_populates="items")
    # joined load, чтобы сразу получать цену и название товара
    product: "Product" = Relationship(sa_relationship_kwargs={"lazy": "joined"})

# --- CRM МОДЕЛИ (ФАЗА 22) ---

class Service(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str = Field(index=True)
    description: Optional[str] = None
    base_price: int = Field(default=0)
    
    order_links: List["OrderServiceLink"] = Relationship(back_populates="service")

    def __str__(self):
        return f"{self.title} ({self.base_price} руб.)"

class OrderProductLink(SQLModel, table=True):
    __tablename__ = "order_product_link"
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    product_id: Optional[int] = Field(default=None, foreign_key="product.id")
    quantity: int = Field(default=1)
    price: int = Field(default=0)  # Фиксируем цену на момент заказа
    
    order: "Order" = Relationship(back_populates="product_links")
    product: "Product" = Relationship(back_populates="order_links")

class OrderServiceLink(SQLModel, table=True):
    __tablename__ = "order_service_link"
    id: Optional[int] = Field(default=None, primary_key=True)
    order_id: Optional[int] = Field(default=None, foreign_key="order.id")
    service_id: Optional[int] = Field(default=None, foreign_key="service.id")
    quantity: int = Field(default=1)
    price: int = Field(default=0)  # Фиксируем цену на момент заказа
    
    order: "Order" = Relationship(back_populates="service_links")
    service: "Service" = Relationship(back_populates="order_links")

class Order(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    # Customer (FK to Customer table)
    customer_id: Optional[int] = Field(default=None, foreign_key="customer.id")
    
    # Delivery address (may differ from customer address)
    delivery_address: Optional[str] = None
    
    # Техническая инфа (для связи с ботом)
    user_id: Optional[int] = Field(default=None, index=True) 
    
    status: str = Field(default="new")  # new, in_progress, done, cancelled
    created_at: datetime = Field(default_factory=datetime.now)
    
    # Relationships
    customer: Optional["Customer"] = Relationship(back_populates="orders")
    product_links: List[OrderProductLink] = Relationship(
        back_populates="order", 
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin"
        }
    )
    service_links: List[OrderServiceLink] = Relationship(
        back_populates="order", 
        sa_relationship_kwargs={
            "cascade": "all, delete-orphan",
            "lazy": "selectin"
        }
    )

    @property
    def total_amount(self):
        p_sum = sum([item.price * item.quantity for item in self.product_links])
        s_sum = sum([item.price * item.quantity for item in self.service_links])
        return p_sum + s_sum

    def __str__(self):
        customer_name = self.customer.name if self.customer else "N/A"
        return f"Заказ #{self.id} ({customer_name})"

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
