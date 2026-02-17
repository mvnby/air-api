from datetime import datetime
from typing import Optional, List

from sqlmodel import Field, Relationship, SQLModel


class Cart(SQLModel, table=True):
    user_id: int = Field(primary_key=True)
    created_at: datetime = Field(default_factory=datetime.now)
    items: List["CartItem"] = Relationship(
        back_populates="cart",
        sa_relationship_kwargs={
            "lazy": "selectin",
            "cascade": "all, delete-orphan",
        },
    )


class CartItem(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    cart_user_id: int = Field(foreign_key="cart.user_id")
    product_id: int = Field(foreign_key="product.id")
    quantity: int = Field(default=1)

    cart: "Cart" = Relationship(back_populates="items")
    product: "Product" = Relationship(sa_relationship_kwargs={"lazy": "joined"})
