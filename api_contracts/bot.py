"""Versioned contracts for the internal Telegram bot API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


BOT_CUSTOMER_REQUISITES_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024


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


BotQuickOrderServiceType = Literal[
    "turnkey",
    "install_only",
    "pre_install",
    "maintenance",
    "repair",
    "dismantling",
]


class BotQuickOrderAddressCheck(BaseModel):
    status: Literal["unchecked", "not_found", "needs_review", "confirmed"]
    message: str = Field(min_length=1, max_length=500)
    suggestion: str | None = Field(default=None, max_length=500)


class BotQuickOrderDraft(BaseModel):
    name: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=64)
    address: str | None = Field(default=None, max_length=1000)
    service_type: BotQuickOrderServiceType | None = None
    service_label: str = Field(min_length=1, max_length=100)
    target_date: datetime | None = None
    request_text: str = Field(min_length=1, max_length=12_000)
    parser: Literal["fallback", "ai"] = "fallback"
    address_check: BotQuickOrderAddressCheck | None = None


class BotQuickOrderParseRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    text: str = Field(min_length=1, max_length=12_000)

    @field_validator("text")
    @classmethod
    def normalize_text(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Quick order text must not be empty")
        return normalized


class BotQuickOrderParseResponse(BaseModel):
    draft: BotQuickOrderDraft


class BotQuickOrderCreateRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    idempotency_key: str = Field(
        min_length=1,
        max_length=160,
        pattern=r"^[A-Za-z0-9._:-]+$",
    )
    draft: BotQuickOrderDraft


class BotQuickOrderCreateResponse(BaseModel):
    order_id: int = Field(ge=1)
    customer_id: int = Field(ge=1)
    created: bool


class BotCustomerBriefResponse(BaseModel):
    id: int = Field(ge=1)
    name: str
    inn: str | None = None
    phone: str | None = None
    email: str | None = None


class BotCustomerRequisitesRecognitionResponse(BaseModel):
    id: int = Field(ge=1)
    status: Literal["recognized", "confirmed", "cancelled"]
    source: str
    extracted: dict[str, Any] = Field(default_factory=dict)
    validation_flags: dict[str, Any] = Field(default_factory=dict)
    duplicate_customer: BotCustomerBriefResponse | None = None
    confirmed_customer_id: int | None = None
    confirmed_action: Literal["create", "update"] | None = None
    created_at: datetime


class BotCustomerRequisitesTextRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    text: str = Field(min_length=20, max_length=12_000)
    telegram_chat_id: int | None = None
    telegram_message_id: int | None = None

    @field_validator("text")
    @classmethod
    def normalize_requisites_text(cls, value: str) -> str:
        normalized = value.strip()
        if len(normalized) < 20:
            raise ValueError("Requisites text is too short")
        return normalized


class BotCustomerRequisitesActionRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    action: Literal["create", "update", "cancel"]


class BotCustomerRequisitesActionResponse(BaseModel):
    recognition: BotCustomerRequisitesRecognitionResponse
    customer: BotCustomerBriefResponse | None = None
    changed: bool
