"""Platform-owner delegation of narrowly defined shared catalog access."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CatalogPermission = Literal["catalog.master.edit", "catalog.master.delete"]


class ManagerAccessItem(BaseModel):
    membership_id: int
    staff_user_id: int
    display_name: str
    tenant_id: int
    tenant_name: str
    role: str
    status: str
    permissions: list[CatalogPermission]
    updated_at: datetime


class ManagerAccessMeta(BaseModel):
    page: int
    limit: int
    total: int
    pages: int


class ManagerAccessList(BaseModel):
    items: list[ManagerAccessItem]
    meta: ManagerAccessMeta


class ManagerAccessUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    permissions: list[CatalogPermission] = Field(max_length=2)
    expected_updated_at: datetime

    @model_validator(mode="after")
    def validate_permissions(self):
        if len(set(self.permissions)) != len(self.permissions):
            raise ValueError("Повторяющиеся разрешения")
        if "catalog.master.delete" in self.permissions and "catalog.master.edit" not in self.permissions:
            raise ValueError("Удаление требует права редактировать каталог")
        return self
