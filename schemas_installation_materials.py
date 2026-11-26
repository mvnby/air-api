from datetime import date
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator


class InstallationMaterialPriceInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=180)
    supplier: str = Field(min_length=1, max_length=120)
    unit: Literal["m", "m2", "piece", "set", "kg", "l", "roll"]
    pack_quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=4)
    pack_price_byn: Decimal = Field(gt=0, max_digits=12, decimal_places=2)
    checked_on: date
    source_url: HttpUrl | None = None
    note: str = Field(default="", max_length=500)


class InstallationMaterialPriceUpdate(InstallationMaterialPriceInput):
    expected_version: int = Field(ge=1)


class InstallationMaterialPriceItem(InstallationMaterialPriceInput):
    model_config = ConfigDict(from_attributes=True)

    id: int
    version: int


class InstallationMaterialPriceList(BaseModel):
    items: list[InstallationMaterialPriceItem]
    has_more: bool


class InstallationMaterialQuantity(BaseModel):
    price_id: int = Field(gt=0)
    quantity: Decimal = Field(gt=0, max_digits=12, decimal_places=4)
    expected_version: int = Field(ge=1)


class InstallationMaterialCostInput(BaseModel):
    items: list[InstallationMaterialQuantity] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_price_ids(self):
        if len({item.price_id for item in self.items}) != len(self.items):
            raise ValueError("Позиции расчёта должны различаться")
        return self


class InstallationMaterialCostLine(BaseModel):
    price_id: int
    quantity: Decimal
    price: InstallationMaterialPriceItem
    total_byn: Decimal


class InstallationMaterialCostResult(BaseModel):
    items: list[InstallationMaterialCostLine]
    total_byn: Decimal
