"""Manager commands for factual maintenance findings; no document/work transitions."""
from datetime import datetime, timezone
from uuid import UUID
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas import ManagerServiceAttachmentItemResponse


class MaintenanceObservationContent(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    equipment_id: int | None = Field(default=None, gt=0)
    equipment_description: str = Field(min_length=1, max_length=2000)
    facts: str = Field(min_length=1, max_length=10000)
    recommendation: str = Field(min_length=1, max_length=10000)


class CreateMaintenanceObservation(MaintenanceObservationContent):
    command_key: UUID
    original_comment: str = Field(min_length=1, max_length=10000)
    observed_at: datetime

    @field_validator("observed_at")
    @classmethod
    def normalize_time(cls, value: datetime) -> datetime:
        if value.tzinfo is None:
            raise ValueError("Observed time requires a timezone")
        return value.astimezone(timezone.utc).replace(tzinfo=None)


class UpdateMaintenanceObservation(MaintenanceObservationContent):
    expected_version: int = Field(ge=1)


class MaintenanceObservationItem(MaintenanceObservationContent):
    model_config = ConfigDict(from_attributes=True)
    id: int
    source_order_id: int
    customer_id: int
    customer_branch_id: int | None
    origin: str
    original_comment: str
    observed_at: datetime
    created_at: datetime
    created_by: str
    updated_at: datetime
    updated_by: str
    version: int


class MaintenanceObservationRevisionItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    version: int
    actor: str
    created_at: datetime
    snapshot: MaintenanceObservationContent


class MaintenanceObservationDetail(MaintenanceObservationItem):
    equipment_link_state: Literal["unlinked", "current", "moved", "archived"] = "unlinked"
    revisions: list[MaintenanceObservationRevisionItem] = Field(default_factory=list)
    photos: list[ManagerServiceAttachmentItemResponse] = Field(default_factory=list)


class MaintenanceObservationList(BaseModel):
    items: list[MaintenanceObservationItem]
    total: int
