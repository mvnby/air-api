"""Shared Manager/MCP contract for physical units attached to an order."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from schemas_connector_mcp import ConnectorInput, WriteInput


class OrderEquipmentReadInput(ConnectorInput):
    order_id: int = Field(gt=0)
    equipment_id: int | None = Field(default=None, gt=0)
    limit: int = Field(default=100, ge=1, le=100)
    offset: int = Field(default=0, ge=0)


class OrderEquipmentSavePayload(WriteInput):
    expected_version: str = Field(min_length=1, max_length=128)
    equipment_id: int | None = Field(default=None, gt=0)
    expected_equipment_version: str | None = Field(default=None, min_length=1, max_length=128)
    source_document_id: int | None = Field(default=None, gt=0)
    brand: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=300)
    serial: str | None = Field(default=None, max_length=300)
    equipment_source: Literal["customer_owned", "sold_by_us"] | None = None
    role: Literal["sale", "installation", "maintenance", "repair", "diagnostic", "warranty_case", "other"] = "installation"

    @field_validator("brand", "model", "serial")
    @classmethod
    def clean_identity(cls, value):
        return (value.strip() or None) if value is not None else None


class OrderEquipmentSaveInput(OrderEquipmentSavePayload):
    order_id: int = Field(gt=0)


class OrderEquipmentIdentity(BaseModel):
    equipment_id: int
    version: str
    customer_id: int
    customer_branch_id: int | None
    catalog_product_id: int | None
    equipment_source: str
    brand: str | None
    model: str | None
    serial: str | None
    roles: list[str]


class OrderEquipmentState(BaseModel):
    order_id: int
    version: str
    items: list[OrderEquipmentIdentity]
    total: int
    candidate: OrderEquipmentIdentity | None = None
    manager_url: str


class OrderEquipmentSaveResult(BaseModel):
    order_id: int
    equipment_id: int
    version: str
    equipment: OrderEquipmentIdentity
    manager_url: str
