"""Manager contracts for public storefront installation rates."""

from enum import Enum

from pydantic import BaseModel, ConfigDict, Field


class ManagerInstallationRateSelectionStatus(str, Enum):
    automatic_fixed = "automatic_fixed"
    matched_manual_quote = "matched_manual_quote"
    legacy_manual_quote = "legacy_manual_quote"
    unsupported = "unsupported"


class ManagerInstallationRateResponse(BaseModel):
    """A public checkout rate with read-only resolver presentation metadata."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    category: str
    power_range: str
    base_price: int
    extra_pipe_price: int
    included_pipe_meters: int
    is_fixed: bool
    comment: str | None = None

    title: str
    equipment_label: str
    power_label: str
    selection_status: ManagerInstallationRateSelectionStatus
    selection_note: str


class ManagerInstallationRateListResponse(BaseModel):
    items: list[ManagerInstallationRateResponse]


class ManagerInstallationRateUpdatePayload(BaseModel):
    """Only checkout prices and explanatory text are editable from Manager."""

    model_config = ConfigDict(extra="forbid")

    base_price: int = Field(ge=0)
    extra_pipe_price: int = Field(ge=0)
    included_pipe_meters: int = Field(ge=0)
    comment: str | None = Field(default=None, max_length=1000)
