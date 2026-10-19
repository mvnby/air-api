"""Editorial compatibility; commercial data remains on Product and tenant offers."""

from sqlalchemy import CheckConstraint
from sqlmodel import Field, SQLModel


class SeriesAccessoryLink(SQLModel, table=True):
    __tablename__ = "series_accessory_link"
    __table_args__ = (
        CheckConstraint("sort_order >= 0", name="ck_series_accessory_sort_order"),
    )

    series_id: int = Field(foreign_key="product_series.id", ondelete="CASCADE", primary_key=True)
    accessory_product_id: int = Field(foreign_key="product.id", ondelete="CASCADE", primary_key=True, index=True)
    sort_order: int = Field(default=0)


class ProductAccessoryOverride(SQLModel, table=True):
    __tablename__ = "product_accessory_override"
    __table_args__ = (
        CheckConstraint("product_id <> accessory_product_id", name="ck_product_accessory_not_self"),
        CheckConstraint("sort_order >= 0", name="ck_product_accessory_sort_order"),
    )

    product_id: int = Field(foreign_key="product.id", ondelete="CASCADE", primary_key=True)
    accessory_product_id: int = Field(foreign_key="product.id", ondelete="CASCADE", primary_key=True, index=True)
    is_enabled: bool = Field(default=True)
    sort_order: int = Field(default=0)
