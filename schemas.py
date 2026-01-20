from typing import List, Optional, Any, Dict
from pydantic import BaseModel
from datetime import datetime
from enum import Enum

# --- SHARED ---

class Meta(BaseModel):
    total: int
    page: int
    limit: int
    pages: int

# --- CATALOG ---

class ProductBase(BaseModel):
    id: int
    title: str
    slug: str
    price: int
    old_price: Optional[int]
    area: int
    is_inverter: bool
    power_cooling: Optional[float]
    main_image: Optional[str]
    is_published: bool
    created_at: datetime

class TagResponse(BaseModel):
    id: int
    title: str
    slug: str
    group_title: Optional[str] = None

class ProductResponse(ProductBase):
    tags: List[TagResponse] = []
    specs: Dict[str, Any] = {}
    images: List[str] = []

class CatalogResponse(BaseModel):
    items: List[ProductResponse]
    meta: Meta

# --- CONTENT ---

class ArticleResponse(BaseModel):
    id: int
    title: str
    slug: str
    content: str
    main_image: Optional[str]
    created_at: datetime

class ServiceResponse(BaseModel):
    id: int
    title: str
    description: Optional[str]
    base_price: int

# --- ORDERS ---

class CartItemPayload(BaseModel):
    product_id: int
    quantity: int = 1

class CustomerPayload(BaseModel):
    name: str
    phone: str
    email: Optional[str] = None
    address: Optional[str] = None # For delivery

class OrderPayload(BaseModel):
    customer: CustomerPayload
    items: List[CartItemPayload]

class OrderResponse(BaseModel):
    id: int
    status: str
    total_amount: float
    created_at: datetime
