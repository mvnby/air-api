"""Stable staff task notification contracts for the autonomous Telegram bot."""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


StaffTaskEventKind = Literal[
    "assigned",
    "rescheduled",
    "canceled",
    "departure_reminder",
]
StaffTaskChangeField = Literal["assignee", "start_time", "end_time", "address"]


class StaffTaskNotificationPayloadV1(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, str_strip_whitespace=True)

    event_kind: StaffTaskEventKind
    staff_user_id: int = Field(gt=0)
    stage_id: int = Field(gt=0)
    order_id: int = Field(gt=0)
    stage_name: str = Field(min_length=1, max_length=200)
    status: str = Field(min_length=1, max_length=40)
    start_time: datetime | None = None
    end_time: datetime | None = None
    timezone: Literal["Europe/Minsk"] = "Europe/Minsk"
    address: str | None = Field(default=None, max_length=500)
    customer_name: str | None = Field(default=None, max_length=200)
    customer_phone: str | None = Field(default=None, max_length=80)
    manager_url: str = Field(min_length=1, max_length=500)
    change_fields: tuple[StaffTaskChangeField, ...] = ()
    reminder_offset_minutes: int | None = Field(default=None, ge=1, le=24 * 60)

    @field_validator("change_fields")
    @classmethod
    def change_fields_are_unique(
        cls, value: tuple[StaffTaskChangeField, ...]
    ) -> tuple[StaffTaskChangeField, ...]:
        if len(set(value)) != len(value):
            raise ValueError("change_fields contains duplicates")
        return value

    @model_validator(mode="after")
    def event_metadata_matches_kind(self) -> "StaffTaskNotificationPayloadV1":
        if self.event_kind == "departure_reminder":
            if self.reminder_offset_minutes is None or self.start_time is None:
                raise ValueError("departure reminder requires time and offset")
        elif self.reminder_offset_minutes is not None:
            raise ValueError("reminder offset is only valid for departure reminders")
        if self.event_kind == "rescheduled" and not self.change_fields:
            raise ValueError("rescheduled event requires change_fields")
        return self


STAFF_TASK_EVENT_TYPES: dict[StaffTaskEventKind, str] = {
    "assigned": "crm.staff_task.assigned",
    "rescheduled": "crm.staff_task.rescheduled",
    "canceled": "crm.staff_task.canceled",
    "departure_reminder": "crm.staff_task.departure_reminder",
}
STAFF_TASK_TEMPLATE_KEYS: dict[StaffTaskEventKind, str] = {
    kind: f"telegram.staff_task_{kind}" for kind in STAFF_TASK_EVENT_TYPES
}
STAFF_TASK_EVENT_TYPE_VALUES = tuple(STAFF_TASK_EVENT_TYPES.values())
STAFF_TASK_TEMPLATE_KEY_VALUES = tuple(STAFF_TASK_TEMPLATE_KEYS.values())
