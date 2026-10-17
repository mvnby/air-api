"""Exact, company/site-scoped worker cash transport; no commercial order DTOs."""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from services.service_estimate_money import exact_money

Currency = Literal["BYN", "USD", "EUR"]


class MoneyCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    idempotency_key: UUID
    expected_version: int = Field(ge=0)


class MoneyAmountCommand(MoneyCommand):
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: Currency

    @field_validator("amount")
    @classmethod
    def exact_amount(cls, value):
        return exact_money(value)


class ClientMoneyReceived(MoneyAmountCommand):
    """expected_version is the displayed collection instruction version."""


class WorkerCashHandoverCreate(MoneyAmountCommand):
    """expected_version is the displayed worker cash account version."""

    recipient_staff_user_id: int = Field(gt=0)


class WorkerCashHandoverAction(MoneyCommand):
    """expected_version is the handover row version."""


class WorkerMoneyCorrection(MoneyCommand):
    reason: str = Field(min_length=3, max_length=500)

    @field_validator("reason")
    @classmethod
    def reason_not_blank(cls, value):
        if len(value.strip()) < 3:
            raise ValueError("Укажите причину исправления")
        return value.strip()


class WorkerMoneyRecipient(BaseModel):
    staff_user_id: int
    display_name: str


class WorkerMoneyRecipients(BaseModel):
    items: list[WorkerMoneyRecipient]
    total: int
    page: int
    limit: int


class WorkerCashBalance(BaseModel):
    currency: Currency
    received: str
    handed_over: str
    held: str
    pending: str
    available: str


class WorkerMoneyEntry(BaseModel):
    id: int
    kind: Literal["client_receipt", "handover", "receipt_reversal"]
    status: Literal[
        "recorded", "pending", "confirmed", "rejected", "cancelled", "reversed"
    ]
    amount: str
    currency: Currency
    created_at: datetime
    order_id: int | None = None
    title: str | None = None
    recipient_staff_user_id: int | None = None
    recipient_name: str | None = None
    version: int = 0
    can_reverse: bool = False


class WorkerMoneyWorkspace(BaseModel):
    worker_profile_id: int | None
    staff_user_id: int
    display_name: str
    version: int
    can_manage: bool
    balances: list[WorkerCashBalance]
    items: list[WorkerMoneyEntry]
    total: int
    page: int
    limit: int


class WorkerMoneyOverviewItem(BaseModel):
    worker_profile_id: int
    staff_user_id: int
    display_name: str
    balances: list[WorkerCashBalance]


class WorkerMoneyOverview(BaseModel):
    items: list[WorkerMoneyOverviewItem]
    total: int
    page: int
    limit: int
    can_manage: bool


class WorkerMoneyCommandResult(BaseModel):
    id: int
    kind: Literal["client_receipt", "handover", "receipt_reversal"]
    status: str
    version: int
    account_version: int
