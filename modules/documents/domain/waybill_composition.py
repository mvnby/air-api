"""Composition of a single paper waybill, separate from the order's product lines."""

from typing import Annotated
from pydantic import BaseModel, ConfigDict, Field


Money = Annotated[str, Field(pattern=r"^[0-9]{1,12}(\.[0-9]{1,2})?$")]
Revision = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class WaybillComponent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=500)
    country: str = Field(default="", max_length=160)
    unit: str = Field(min_length=1, max_length=40)
    quantity_per_parent: int = Field(gt=0, le=1_000_000)
    unit_price: Money


class WaybillLineSelection(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order_product_line_id: int = Field(gt=0)
    whole_country: str | None = Field(default=None, max_length=160)
    # null means the whole product, even if a split is configured in the catalog.
    components: list[WaybillComponent] | None = Field(
        default=None, min_length=1, max_length=100
    )


class WaybillComposition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_revision: Revision
    lines: list[WaybillLineSelection] = Field(min_length=1, max_length=500)


class WaybillSourceLine(BaseModel):
    order_product_line_id: int
    components: list[WaybillComponent] | None
    product_id: int | None
    title: str
    country: str
    quantity: int
    unit_price: Money


class WaybillCompositionSource(BaseModel):
    source_revision: Revision
    lines: list[WaybillSourceLine]
