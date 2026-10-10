"""Explicit customer-facing catalog selection and native draft commands."""

from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from schemas_connector_mcp import ConnectorInput, WriteInput


class CatalogSelectionInput(ConnectorInput):
    cooling_btu_class: Literal[7, 9, 12, 18, 24, 30, 36, 42, 60] | None = None
    area_m2: int | None = Field(default=None, ge=1, le=200)
    quantity: int = Field(default=1, ge=1, le=100)
    budget_byn: int | None = Field(default=None, gt=0, le=10_000_000)
    budget_scope: Literal["per_unit", "total"] = "per_unit"
    is_inverter: bool | None = None
    heating_min_c: int | None = Field(default=None, ge=-40, le=15)
    has_wifi: bool | None = None
    brand_slugs: list[str] = Field(default_factory=list, max_length=20)
    query: str | None = Field(default=None, min_length=1, max_length=200)
    in_stock_only: bool = False

    @model_validator(mode="after")
    def require_size(self):
        if self.cooling_btu_class is None and self.area_m2 is None:
            raise ValueError("Specify cooling class or room area before selection")
        return self


class CatalogProductInput(ConnectorInput):
    product_id: int = Field(gt=0)


class CatalogProduct(BaseModel):
    product_id: int
    title: str
    brand: str | None
    series: str | None
    unit_price_byn: int
    currency: Literal["BYN"] = "BYN"
    site_url: str | None
    is_inverter: bool
    cooling_power_kw: float | None
    area_m2: float | None
    heating_min_c: float | None
    wifi: Literal["builtin", "ready", "none", "unknown"]
    availability: Literal["in_stock", "on_request"]


class CatalogSelectionOption(BaseModel):
    label: str
    reason: str
    product: CatalogProduct
    quantity: int
    equipment_total_byn: int


class CatalogSelectionResult(BaseModel):
    mode: Literal["price_tiers", "budget_brands"]
    checked_at: datetime
    options: list[CatalogSelectionOption]
    matching_products: int
    distinct_brands: int
    warnings: list[str]
    message_text: str
    installation_included: Literal[False] = False


class CatalogDocumentLine(ConnectorInput):
    product_id: int = Field(gt=0)
    quantity: int = Field(ge=1, le=100)
    expected_unit_price_byn: int = Field(gt=0)


class CatalogDocumentInput(WriteInput):
    order_id: int = Field(gt=0)
    customer_id: int = Field(gt=0)
    legal_entity_id: int = Field(gt=0)
    document_type: Literal["offer", "invoice"]
    issue_date: date
    template_id: int | None = Field(default=None, gt=0)
    lines: list[CatalogDocumentLine] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def distinct_products(self):
        ids = [line.product_id for line in self.lines]
        if len(ids) != len(set(ids)):
            raise ValueError("Combine quantities for a repeated product")
        return self


class CatalogDocumentResult(BaseModel):
    order_id: int
    customer_id: int
    proposal_id: int
    document_id: int
    document_type: Literal["offer", "invoice"]
    status: Literal["draft"] = "draft"
    equipment_total_byn: int
    currency: Literal["BYN"] = "BYN"
    manager_url: str
    installation_included: Literal[False] = False


class CatalogIssuer(BaseModel):
    legal_entity_id: int
    display_name: str
    is_default: bool


class CatalogIssuersResult(BaseModel):
    items: list[CatalogIssuer]
