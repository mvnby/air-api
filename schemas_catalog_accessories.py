"""Compatibility workspaces and a deliberately small public accessory card."""

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class SeriesAccessoriesUpdate(BaseModel):
    accessory_product_ids: list[int] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_ids(self):
        ids = self.accessory_product_ids
        if any(value < 1 for value in ids) or len(set(ids)) != len(ids):
            raise ValueError("Укажите уникальные положительные ID аксессуаров.")
        return self


class ProductAccessoryOverridePayload(BaseModel):
    accessory_product_id: int = Field(ge=1)
    is_enabled: bool


class ProductAccessoriesUpdate(BaseModel):
    overrides: list[ProductAccessoryOverridePayload] = Field(default_factory=list, max_length=100)

    @model_validator(mode="after")
    def validate_ids(self):
        ids = [item.accessory_product_id for item in self.overrides]
        if len(set(ids)) != len(ids):
            raise ValueError("Аксессуар не может повторяться в исключениях модели.")
        return self


class ManagerAccessoryItem(BaseModel):
    accessory_product_id: int
    title: str
    slug: str
    accessory_type: str | None = None
    is_published: bool
    inherited: bool
    override: bool | None = None
    is_enabled: bool


class ManagerAccessoriesWorkspace(BaseModel):
    target_type: Literal["series", "product"]
    target_id: int
    series_id: int | None = None
    items: list[ManagerAccessoryItem] = Field(default_factory=list)


class PublicCatalogAccessory(BaseModel):
    product_id: int
    title: str
    slug: str
    accessory_type: str | None = None
    main_image: str | None = None
    price: int
    old_price: int | None = None
    availability_status: str | None = None
    delivery_min_days: int | None = None
    delivery_max_days: int | None = None
    compatibility_source: Literal["series", "product"]
    suggested_for_purchase: bool = Field(default=True, description="Wi-Fi modules are suggested only for a model explicitly marked Wi-Fi Ready; compatibility alone never changes capability.")
