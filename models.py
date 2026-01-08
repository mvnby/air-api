from typing import Optional, List, Dict, Any
from sqlmodel import SQLModel, Field, JSON, Column
from datetime import datetime

class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    
    title: str = Field(index=True)
    description: str = Field(default="")
    
    price: int
    old_price: Optional[int] = None
    area: int = Field(default=0, index=True)
    
    # --- ИЗМЕНЕНИЯ ТУТ ---
    # 1. Главная картинка (строка). Легко редактировать, всегда одна.
    main_image: Optional[str] = Field(default=None)
    
    # 2. Галерея (список). JSON для слайдера внутри карточки.
    images: List[str] = Field(default=[], sa_column=Column(JSON))
    # ---------------------

    categories: List[str] = Field(default=[], sa_column=Column(JSON))
    specs: Dict[str, Any] = Field(default={}, sa_column=Column(JSON))
    
    is_published: bool = Field(default=True)
    created_at: datetime = Field(default_factory=datetime.now)

class Article(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    title: str
    content: str
    image_url: Optional[str] = None
    created_at: datetime = Field(default_factory=datetime.now)