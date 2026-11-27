"""Two local calendar days for a manager in the selected company and storefront."""

import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, HttpUrl


class BotScheduleRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    telegram_id: int = Field(gt=0)
    expected_context_version: int = Field(ge=0)


class BotScheduleEvent(BaseModel):
    id: str
    date: datetime.date = Field(description="Display day in Europe/Minsk.")
    time: str | None = Field(
        pattern=r"^(?:[01]\d|2[0-3]):[0-5]\d$",
        description="Local HH:MM for an appointment, null for a reminder.",
    )
    type: Literal["measurement", "installation", "work_stage", "equipment_maintenance"]
    title: str
    status: str
    customer_name: str | None
    customer_phone: str | None
    address: str | None
    order_id: int | None = Field(gt=0)
    order_url: HttpUrl | None
    due_date: datetime.date | None = Field(description="Original due date of a maintenance reminder, including when overdue.")


class BotScheduleResponse(BaseModel):
    today: datetime.date
    tomorrow: datetime.date
    timezone: Literal["Europe/Minsk"] = "Europe/Minsk"
    events: list[BotScheduleEvent]
