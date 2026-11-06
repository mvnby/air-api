from datetime import datetime
from typing import Annotated, Self

from pydantic import ConfigDict, Field, field_validator, model_validator
from pydantic.dataclasses import dataclass


WAYBILL_DOCUMENT_TYPES = frozenset({"tn2", "ttn1"})
LOCAL_MINUTE = r"^[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}$"


@dataclass(frozen=True, config=ConfigDict(extra="forbid", str_strip_whitespace=True))
class TransportOperation:
    """Local civil times as recorded on the paper consignment note."""

    performer: Annotated[str, Field(max_length=300)] | None = None
    method: Annotated[str, Field(max_length=200)] | None = None
    arrived_at: Annotated[str, Field(pattern=LOCAL_MINUTE)] | None = None
    departed_at: Annotated[str, Field(pattern=LOCAL_MINUTE)] | None = None
    downtime_minutes: (
        Annotated[int, Field(ge=0, le=2_147_483_647, strict=True)] | None
    ) = None

    @field_validator("arrived_at", "departed_at")
    @classmethod
    def valid_local_minute(cls, value):
        if value is not None:
            try:
                datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError("Проверьте дату и время операции") from exc
        return value

    @model_validator(mode="after")
    def times_in_order(self) -> Self:
        if self.arrived_at and self.departed_at and self.departed_at < self.arrived_at:
            raise ValueError("Убытие не может быть раньше прибытия")
        return self


@dataclass(frozen=True)
class TransportTerms:
    """Transport facts frozen into a native paper waybill draft."""

    car_model: str | None = None
    car_number: str | None = None
    driver_name: str | None = None
    carrier: str | None = None
    trip_sheet_number: str | None = None
    freight_payer: str | None = None
    loading_point: str | None = None
    unloading_point: str | None = None
    loading: TransportOperation | None = None
    unloading: TransportOperation | None = None
