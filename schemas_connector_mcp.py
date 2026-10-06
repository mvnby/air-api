"""Compact, explicit projections and query inputs for the Kitlane MCP boundary."""

from datetime import datetime

from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict, Field, field_validator

from schemas_personal_tasks import (
    PersonalTaskCreatePayload,
    PersonalTaskListFilter,
    PersonalTaskListResponse,
    PersonalTaskResponse,
    PersonalTaskUpdatePayload,
)
from schemas_incoming import IncomingCreatePayload, IncomingUpdatePayload


class ConnectorInput(BaseModel):
    model_config = ConfigDict(extra="forbid")


class EmptyInput(ConnectorInput):
    pass


class SearchInput(ConnectorInput):
    query: str = Field(min_length=1, max_length=200)
    limit: int = Field(default=10, ge=1, le=20)

    @field_validator("query")
    @classmethod
    def nonempty_query(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Search text is required")
        return value.strip()


class CustomerIdInput(ConnectorInput):
    customer_id: int = Field(gt=0)


class OrderIdInput(ConnectorInput):
    order_id: int = Field(gt=0)


class ConnectorContext(BaseModel):
    staff_user_id: int
    username: str
    tenant_id: int
    storefront_id: int
    timezone: str
    current_time: datetime
    manager_url: str


class CustomerSummary(BaseModel):
    id: int
    name: str
    phone: str
    email: str | None
    type: str
    city: str | None
    archived: bool
    link: str


class CustomerSearchResult(BaseModel):
    items: list[CustomerSummary]
    ambiguous: bool
    has_more: bool


class OrderSummary(BaseModel):
    id: int
    title: str | None
    status: str
    customer_id: int | None
    customer_name: str | None
    delivery_address: str | None
    total_amount: float
    balance_due: float
    link: str


class OrderSearchResult(BaseModel):
    items: list[OrderSummary]
    ambiguous: bool
    has_more: bool


class WriteInput(ConnectorInput):
    idempotency_key: str = Field(min_length=16, max_length=128, pattern=r"^[A-Za-z0-9._:-]+$")


class ConnectorTaskCreatePayload(PersonalTaskCreatePayload):
    model_config = ConfigDict(extra="forbid")

    @field_validator("due_at", "reminder_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        if value is not None and (value.tzinfo is None or value.utcoffset() is None):
            raise ValueError("Task dates must include an explicit timezone offset")
        return value


class ConnectorTaskUpdatePayload(PersonalTaskUpdatePayload):
    model_config = ConfigDict(extra="forbid")

    @field_validator("due_at", "reminder_at")
    @classmethod
    def require_timezone(cls, value: datetime | None) -> datetime | None:
        return ConnectorTaskCreatePayload.require_timezone(value)


class TaskCreateInput(WriteInput):
    payload: ConnectorTaskCreatePayload


class TaskIdInput(ConnectorInput):
    task_id: int = Field(gt=0)


class TaskUpdateInput(WriteInput):
    task_id: int = Field(gt=0)
    payload: ConnectorTaskUpdatePayload


class TaskStatusInput(WriteInput):
    task_id: int = Field(gt=0)
    expected_version: int = Field(ge=1)


class TaskListInput(ConnectorInput):
    task_filter: PersonalTaskListFilter = "active"
    limit: int = Field(default=20, ge=1, le=50)
    offset: int = Field(default=0, ge=0, le=10000)


class ConnectorTaskResponse(PersonalTaskResponse):
    manager_url: str


class ConnectorTaskListResponse(PersonalTaskListResponse):
    items: list[ConnectorTaskResponse]


class IncomingCreateInput(WriteInput):
    payload: IncomingCreatePayload


class IncomingIdInput(ConnectorInput):
    lead_id: int = Field(gt=0)


class IncomingUpdateInput(WriteInput):
    lead_id: int = Field(gt=0)
    payload: IncomingUpdatePayload


class IncomingListInput(ConnectorInput):
    limit: int = Field(default=10, ge=1, le=20)
    offset: int = Field(default=0, ge=0, le=10000)


ResultT = TypeVar("ResultT", bound=BaseModel)


class ConnectorWriteResult(BaseModel, Generic[ResultT]):
    result: ResultT
    replayed: bool
