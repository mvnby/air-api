"""Versioned contracts for the internal Telegram bot API."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator


class BotApiHealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    api_version: Literal["v1"] = "v1"


class BotStaffContextResponse(BaseModel):
    telegram_id: int = Field(ge=1)
    is_staff: bool = False
    display_name: str = ""
    primary_role: str = ""
    roles: list[str] = Field(default_factory=list)
    legacy_installer_id: int | None = None
    is_manager: bool = False
    is_executor: bool = False


class BotCatalogProductResponse(BaseModel):
    """Small, stable product projection used by Telegram catalog cards."""

    id: int = Field(ge=1)
    title: str
    slug: str = ""
    description: str = ""
    price: int
    area: int = 0
    main_image: str | None = None
    categories: list[str] = Field(default_factory=list)
    vitebsk_qty: int = 0
    minsk_qty: int = 0
    availability_status: str = "out_of_stock"


class BotCatalogSearchRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    query: str = Field(min_length=1, max_length=100)
    limit: int = Field(default=5, ge=1, le=10)


class BotCatalogSearchResponse(BaseModel):
    items: list[BotCatalogProductResponse] = Field(default_factory=list)


class BotCatalogProductLookupResponse(BaseModel):
    product: BotCatalogProductResponse | None = None


class BotTaskListRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    limit: int = Field(default=10, ge=1, le=20)


class BotTaskResponse(BaseModel):
    """Stable read-only task projection rendered by the Telegram runtime."""

    kind: Literal["stage", "order"]
    id: int = Field(ge=1)
    order_id: int = Field(ge=1)
    title: str
    status: str
    start_time: datetime
    address: str | None = None
    customer_name: str = "Клиент"
    customer_phone: str | None = None
    comment: str | None = None


class BotTaskListResponse(BaseModel):
    items: list[BotTaskResponse] = Field(default_factory=list)


class BotTaskStatusUpdateRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    status: Literal["in_progress", "completed"]


class BotTaskStatusUpdateResponse(BaseModel):
    stage_id: int = Field(ge=1)
    status: Literal["in_progress", "completed"]
    changed: bool


class BotTaskReportSaveRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    report: str = Field(min_length=1, max_length=12_000)

    @field_validator("report")
    @classmethod
    def normalize_report(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Task report must not be empty")
        return normalized


class BotTaskReportSaveResponse(BaseModel):
    stage_id: int = Field(ge=1)
    changed: bool
