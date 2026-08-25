"""Explicit response contracts for public catalog helper endpoints."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr, model_serializer

from schemas import ProductKind, PublicStockState


class PublicProductSearchItemResponse(BaseModel):
    """Small public projection; internal sourcing and margin data is excluded."""

    model_config = ConfigDict(extra="forbid")

    id: int
    title: str
    slug: str | None = None
    price: int
    old_price: int | None = None
    installation_discount: int = 0
    product_kind: ProductKind = "unknown"
    is_inverter: bool
    power_cooling: float | None = None
    main_image: str | None = None
    card_image: str | None = None
    full_image: str | None = None
    specs: dict[str, Any] = Field(default_factory=dict)
    vitebsk_qty: int = 0
    minsk_qty: int = 0
    availability_status: str | None = None
    public_stock_state: PublicStockState | None = None
    delivery_min_days: int | None = None
    delivery_max_days: int | None = None
    _disclose_legacy_availability: bool = PrivateAttr(default=True)

    @model_serializer(mode="wrap")
    def _serialize_availability_disclosure(self, handler):
        payload = handler(self)
        if not self._disclose_legacy_availability:
            payload.pop("vitebsk_qty", None)
            payload.pop("minsk_qty", None)
            payload.pop("public_stock_state", None)
        return payload


class PublicProductSearchResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[PublicProductSearchItemResponse] = Field(default_factory=list)
