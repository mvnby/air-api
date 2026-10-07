"""Persistent incoming requests; desired dates never schedule work."""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

from core.input_validation import validate_optional_email, validate_optional_phone


class IncomingFields(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_text: str = Field(min_length=1, max_length=12000)
    name: str | None = Field(default=None, max_length=200)
    phone: str | None = None
    email: str | None = None
    region_text: str | None = Field(default=None, max_length=300)
    workflow_type: Literal["sales_installation", "service_work", "maintenance", "repair"] | None = None
    service_type: Literal["turnkey", "install_only", "pre_install", "maintenance", "repair", "dismantling"] | None = None
    address_text: str | None = Field(default=None, max_length=500)
    requested_time_text: str | None = Field(default=None, max_length=300)
    requested_at: AwareDatetime | None = None
    call_before_visit: bool | None = Field(default=None, description="Prior-call agreement, independent of a confirmed visit or task deadline.")
    clarification_requested: bool | None = Field(default=None, description="Explicit instruction to save one linked clarification task. On creation, omission also recognizes standalone positive address/call instructions; false disables that text inference. MCP requires task-write scope when a task is requested.")

    @model_validator(mode="after")
    def valid_scenario(self):
        from services.order_scenarios import resolve_scenario
        resolve_scenario(workflow_type=self.workflow_type, service_type=self.service_type)
        return self

    @field_validator("request_text")
    @classmethod
    def nonempty_text(cls, value):
        if not value.strip():
            raise ValueError("Request text is required")
        return value

    @field_validator("phone")
    @classmethod
    def valid_phone(cls, value):
        return validate_optional_phone(value)

    @field_validator("email")
    @classmethod
    def valid_email(cls, value):
        return validate_optional_email(value)


class IncomingCreatePayload(IncomingFields):
    source_occurred_at: AwareDatetime | None = None
    source_timezone: str = "Europe/Minsk"
    source_event_id: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("source_timezone")
    @classmethod
    def valid_timezone(cls, value):
        try:
            ZoneInfo(value)
        except (ValueError, ZoneInfoNotFoundError) as exc:
            raise ValueError("Unknown timezone") from exc
        return value


class IncomingUpdatePayload(IncomingFields):
    expected_version: int = Field(ge=1)


class IncomingPreview(BaseModel):
    state: Literal["suggested", "unknown", "unavailable"]
    region_text: str | None = None
    workflow_type: str | None = None
    service_type: str | None = None
    evidence: dict[str, str] = Field(default_factory=dict)
    field_sources: dict[str, str] = Field(default_factory=dict)


class IncomingResponse(IncomingFields):
    preview: IncomingPreview | None = None
    lead_id: int
    version: int
    intake_state: Literal["needs_contact", "needs_details", "ready_for_review"]
    missing_fields: list[str]
    source_occurred_at: datetime | None
    source_timezone: str
    original_text: str
    date_precision: Literal["date", "datetime"] | None = None
    field_sources: dict[str, str] = Field(default_factory=dict)
    clarification_task_id: int | None = None
    manager_url: str


class IncomingListResponse(BaseModel):
    items: list[IncomingResponse]
    total: int


class IncomingClarificationPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")
    expected_version: int = Field(ge=1)


class IncomingOrderContext(IncomingFields):
    model_config = ConfigDict(extra="ignore")
    lead_id: int
    lead_version: int
    original_text: str
    source_occurred_at: datetime | None = None
    source_timezone: str
    date_precision: Literal["date", "datetime"] | None = None
    field_sources: dict[str, str] = Field(default_factory=dict)
    clarification_task_id: int | None = None
    agreement_status: Literal["customer_wish"] = "customer_wish"
