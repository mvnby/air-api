"""Shared Manager and MCP contracts for order sites and physical units."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from schemas import ManagerEquipmentDetailResponse
from schemas_connector_mcp import ConnectorInput, WriteInput


EquipmentRole = Literal["sale", "installation", "maintenance", "repair", "diagnostic", "warranty_case", "other"]


class OrderSiteAddPayload(ConnectorInput):
    customer_branch_id: int | None = Field(default=None, gt=0)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    address: str | None = Field(default=None, min_length=1, max_length=1000)

    @field_validator("title", "address", mode="before")
    @classmethod
    def trim_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @model_validator(mode="after")
    def require_order_only_address(self):
        if self.customer_branch_id is None and not (self.title and self.address):
            raise ValueError("Укажите филиал или название и адрес объекта")
        return self


class OrderSiteEquipmentComponent(ConnectorInput):
    component_type: Literal["indoor_unit", "outdoor_unit", "drain_pump", "other"]
    title: str | None = Field(default=None, max_length=200)
    brand: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=300)
    serial: str | None = Field(default=None, max_length=300)
    inventory_number: str | None = Field(default=None, max_length=300)
    notes: str | None = Field(default=None, max_length=2000)


class OrderSiteNewEquipment(ConnectorInput):
    equipment_type: str = Field(default="hvac", min_length=1, max_length=64)
    display_name: str | None = Field(default=None, max_length=200)
    brand: str | None = Field(default=None, max_length=200)
    model: str | None = Field(default=None, max_length=300)
    serial: str | None = Field(default=None, max_length=300)
    inventory_number: str | None = Field(default=None, max_length=300)
    location_hint: str | None = Field(default=None, max_length=500)
    refrigerant_type: str | None = Field(default=None, max_length=64)
    installed_at: datetime | None = None
    notes: str | None = Field(default=None, max_length=2000)
    components: list[OrderSiteEquipmentComponent] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def require_identity_or_description(self):
        identity = (self.display_name, self.model, self.serial, self.inventory_number)
        if not any(value and value.strip() for value in identity) and not self.components:
            raise ValueError("Укажите описание, модель, номер или состав оборудования")
        return self


class OrderSiteEquipmentLinkPayload(ConnectorInput):
    equipment_id: int | None = Field(default=None, gt=0)
    equipment: OrderSiteNewEquipment | None = None
    role: EquipmentRole = "diagnostic"
    expected_version: int = Field(ge=1)

    @model_validator(mode="after")
    def require_one_equipment_reference(self):
        if (self.equipment_id is None) == (self.equipment is None):
            raise ValueError("Укажите существующее оборудование или данные для создания нового")
        return self


class OrderSiteAddRequest(WriteInput):
    payload: OrderSiteAddPayload


class OrderSiteEquipmentLinkRequest(WriteInput):
    payload: OrderSiteEquipmentLinkPayload


class OrderSiteLegacyPrimary(BaseModel):
    customer_branch_id: int | None
    title: str
    address: str


class OrderSiteItem(OrderSiteLegacyPrimary):
    id: int
    order_id: int
    version: int
    manager_url: str


class OrderSiteList(BaseModel):
    items: list[OrderSiteItem]
    total: int
    limit: int
    offset: int
    legacy_primary: OrderSiteLegacyPrimary | None


class OrderSiteEquipmentItem(BaseModel):
    equipment_id: int
    site_id: int
    role: EquipmentRole
    equipment: ManagerEquipmentDetailResponse


class OrderSiteEquipmentList(BaseModel):
    items: list[OrderSiteEquipmentItem]
    total: int
    limit: int
    offset: int


class OrderSiteEquipmentLinkResult(BaseModel):
    site: OrderSiteItem
    equipment: OrderSiteEquipmentItem
