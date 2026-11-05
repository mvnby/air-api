"""Inputs and results for proposal-scoped service editing."""

from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from schemas_connector_mcp import ConnectorInput, WriteInput
from services.service_estimate_money import exact_money


class ServiceOrderProposalInput(ConnectorInput):
    order_id: int = Field(gt=0)
    proposal_id: int = Field(gt=0)


class ServiceOrderLineInput(ConnectorInput):
    title: str = Field(min_length=1, max_length=1000)
    description: str | None = Field(default=None, max_length=10000)
    unit: str = Field(min_length=1, max_length=100)
    quantity: int = Field(gt=0, le=1000000)
    price: Decimal = Field(ge=0, max_digits=14, decimal_places=2)

    @field_validator("title", "unit")
    @classmethod
    def clean_required(cls, value):
        value = value.strip()
        if not value:
            raise ValueError("Value must not be blank")
        return value

    @field_validator("price")
    @classmethod
    def validate_price(cls, value):
        return exact_money(value)


class ServiceOrderProposalEditInput(ServiceOrderProposalInput, WriteInput):
    expected_version: str = Field(min_length=1, max_length=128)
    action: Literal["add", "update", "delete"]
    line_id: int | None = Field(default=None, gt=0)
    line: ServiceOrderLineInput | None = None


class ServiceOrderLineResult(BaseModel):
    id: int
    service_id: int | None = None
    title: str
    description: str | None
    unit: str
    quantity: int
    price: Decimal
    line_total: Decimal


class ServiceOrderProductResult(BaseModel):
    id: int
    product_id: int | None
    title: str
    quantity: int
    price: Decimal
    line_total: Decimal


class ServiceOrderProposalResult(BaseModel):
    order_id: int
    proposal_id: int
    proposal_status: str
    version: str
    lines: list[ServiceOrderLineResult]
    products: list[ServiceOrderProductResult]
    total: Decimal
    currency: str
    manager_url: str
