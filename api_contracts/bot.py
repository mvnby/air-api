"""Versioned contracts for the internal Telegram bot API."""

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


BOT_CUSTOMER_REQUISITES_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
BOT_UPLOAD_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024
BOT_VOICE_MAX_FILE_SIZE_BYTES = 8 * 1024 * 1024
BOT_VOICE_MAX_DURATION_SECONDS = 180


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
    date_from: datetime | None = None
    date_to: datetime | None = None
    statuses: list[
        Literal[
            "planned",
            "in_progress",
            "completed",
            "canceled",
            "new_lead",
            "negotiation",
            "execution",
            "closed",
        ]
    ] = Field(default_factory=list, max_length=8)

    @model_validator(mode="after")
    def validate_date_range(self) -> "BotTaskListRequest":
        if self.date_from and self.date_to:
            from_is_aware = self.date_from.tzinfo is not None
            to_is_aware = self.date_to.tzinfo is not None
            if from_is_aware != to_is_aware:
                raise ValueError("date_from and date_to must use the same timezone form")
            if self.date_from > self.date_to:
                raise ValueError("date_from must not be after date_to")
        return self


class BotTaskResponse(BaseModel):
    """Stable read-only task projection rendered by the Telegram runtime."""

    kind: Literal["stage", "order"]
    id: int = Field(ge=1)
    order_id: int = Field(ge=1)
    stage_id: int | None = Field(default=None, ge=1)
    title: str
    status: str
    start_time: datetime
    address: str | None = None
    customer_name: str = "Клиент"
    customer_phone: str | None = None
    comment: str | None = None
    manager_url: str | None = None


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


class BotVoiceQuickOrderParseResponse(BaseModel):
    transcript: str = Field(min_length=1, max_length=12_000)
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


class BotOrderBriefResponse(BaseModel):
    id: int = Field(ge=1)
    title: str | None = None
    status: str
    workflow_type: str | None = None
    customer_name: str | None = None
    customer_phone: str | None = None
    address: str | None = None
    installation_date: datetime | None = None
    updated_at: datetime | None = None
    created_at: datetime | None = None


class BotOrderListRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    limit: int = Field(default=5, ge=1, le=10)


class BotOrderListResponse(BaseModel):
    items: list[BotOrderBriefResponse] = Field(default_factory=list)
    scope: str | None = None


class BotOrderAttachmentResponse(BaseModel):
    order_id: int = Field(ge=1)
    already_attached: bool = False


class BotNameplateRecognitionResponse(BaseModel):
    order_id: int = Field(ge=1)
    unit_type: Literal["indoor_unit", "outdoor_unit"] | None = None
    raw_text: str
    extracted: dict[str, Any] = Field(default_factory=dict)
    validation_flags: dict[str, Any] = Field(default_factory=dict)
    merge_preview: dict[str, Any] = Field(default_factory=dict)


class BotNameplateApplyResponse(BaseModel):
    result: dict[str, Any]


class BotProductSelectionRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    query: str = Field(min_length=1, max_length=1000)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("Selection query must not be empty")
        return normalized


class BotProductSelectionResponse(BaseModel):
    selection: dict[str, Any]


class BotCuratedProductsRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    area: int = Field(ge=8, le=200)
    is_inverter: bool
    tag_slugs: list[str] = Field(default_factory=list, max_length=10)
    limit: int = Field(default=5, ge=1, le=10)


class BotCuratedProductsResponse(BaseModel):
    items: list[BotCatalogProductResponse] = Field(default_factory=list)


class BotProductPriceUpdateRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    price: int = Field(ge=0, le=10_000_000)


class BotProductMutationRequest(BaseModel):
    telegram_id: int = Field(ge=1)


class BotProductMutationResponse(BaseModel):
    product_id: int = Field(ge=1)
    changed: bool


class BotRepairDraftRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    order_id: int = Field(ge=1)
    comment: str | None = Field(default=None, max_length=4000)
    fault_type: str | None = Field(default=None, max_length=120)


class BotRepairDraftResponse(BaseModel):
    draft: dict[str, Any]


class BotRepairApplyRequest(BaseModel):
    telegram_id: int = Field(ge=1)
    order_id: int = Field(ge=1)
    repair_meta_draft: dict[str, Any]
    raw_comment: str = Field(max_length=4000)
    telegram_chat_id: int | None = None
    telegram_message_id: int | None = None


class BotRepairApplyResponse(BaseModel):
    result: dict[str, Any]


class BotFsmStateGetRequest(BaseModel):
    storage_key: str = Field(min_length=1, max_length=1000)


class BotFsmStateResponse(BaseModel):
    state: str | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class BotFsmStateUpdateRequest(BaseModel):
    storage_key: str = Field(min_length=1, max_length=1000)
    bot_id: int
    chat_id: int
    user_id: int
    thread_id: int | None = None
    business_connection_id: str | None = Field(default=None, max_length=500)
    destiny: str = Field(default="default", min_length=1, max_length=120)
    write_state: bool = False
    state: str | None = Field(default=None, max_length=500)
    write_data: bool = False
    data: dict[str, Any] = Field(default_factory=dict)


class BotRuntimeLeaseRequest(BaseModel):
    name: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    owner_id: str = Field(min_length=1, max_length=160, pattern=r"^[A-Za-z0-9._:-]+$")
    ttl_seconds: int = Field(default=45, ge=15, le=300)


class BotRuntimeLeaseResponse(BaseModel):
    name: str
    owner_id: str
    acquired: bool
    expires_at: datetime | None = None
