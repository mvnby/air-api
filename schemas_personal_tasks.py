"""API contracts for persistent personal tasks."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator


PersonalTaskStatus = Literal["active", "completed", "cancelled"]
PersonalTaskListFilter = Literal[
    "active",
    "today",
    "overdue",
    "undated",
    "completed",
    "cancelled",
]


def _clean_required_text(value: str) -> str:
    cleaned = " ".join(str(value or "").split())
    if not cleaned:
        raise ValueError("Текст поручения обязателен")
    return cleaned


def _clean_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    cleaned = value.strip()
    return cleaned or None


class PersonalTaskCreatePayload(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    description: str | None = Field(default=None, max_length=12_000)
    assignee_staff_user_id: int | None = Field(default=None, gt=0)
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    lead_id: int | None = Field(default=None, gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    order_id: int | None = Field(default=None, gt=0)
    equipment_id: int | None = Field(default=None, gt=0)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str) -> str:
        return _clean_required_text(value)

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)


class PersonalTaskUpdatePayload(BaseModel):
    expected_version: int = Field(ge=1)
    text: str | None = Field(default=None, max_length=2000)
    description: str | None = Field(default=None, max_length=12_000)
    assignee_staff_user_id: int | None = Field(default=None, gt=0)
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    lead_id: int | None = Field(default=None, gt=0)
    customer_id: int | None = Field(default=None, gt=0)
    order_id: int | None = Field(default=None, gt=0)
    equipment_id: int | None = Field(default=None, gt=0)

    @field_validator("text")
    @classmethod
    def validate_text(cls, value: str | None) -> str | None:
        return _clean_required_text(value) if value is not None else None

    @field_validator("description")
    @classmethod
    def validate_description(cls, value: str | None) -> str | None:
        return _clean_optional_text(value)

    @model_validator(mode="after")
    def require_change(self):
        if self.model_fields_set == {"expected_version"}:
            raise ValueError("Укажите хотя бы одно изменение")
        return self


class PersonalTaskStatusPayload(BaseModel):
    expected_version: int = Field(ge=1)


class PersonalTaskResponse(BaseModel):
    id: int
    text: str
    description: str | None = None
    status: PersonalTaskStatus
    version: int
    author_staff_user_id: int
    author_name: str
    assignee_staff_user_id: int | None = None
    assignee_name: str | None = None
    due_at: datetime | None = None
    reminder_at: datetime | None = None
    reminder_due: bool = False
    lead_id: int | None = None
    customer_id: int | None = None
    order_id: int | None = None
    equipment_id: int | None = None
    completed_at: datetime | None = None
    cancelled_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class PersonalTaskListResponse(BaseModel):
    items: list[PersonalTaskResponse]
    total: int
    limit: int
    offset: int
    filter: PersonalTaskListFilter
    due_reminder_count: int


class PersonalTaskAssigneeResponse(BaseModel):
    id: int
    display_name: str


class PersonalTaskAssigneeListResponse(BaseModel):
    items: list[PersonalTaskAssigneeResponse]
