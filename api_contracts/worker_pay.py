"""Exact worker remuneration, independent of customer payments and cash custody."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel, Field, field_validator

from api_contracts.worker_money import (
    MoneyAmountCommand,
    MoneyCommand,
    WorkerMoneyCorrection,
)
from services.service_estimate_money import exact_money


class WorkerPayAgreementCreate(MoneyAmountCommand):
    assignment_id: int = Field(gt=0)
    cost_byn_amount: Decimal | None = Field(
        default=None, gt=0, max_digits=14, decimal_places=2
    )

    @field_validator("cost_byn_amount")
    @classmethod
    def exact_cost(cls, value):
        return exact_money(value) if value is not None else None


class WorkerPayAgreementRevise(MoneyAmountCommand):
    expected_agreement_version: int = Field(ge=0)
    cost_byn_amount: Decimal | None = Field(
        default=None, gt=0, max_digits=14, decimal_places=2
    )

    @field_validator("cost_byn_amount")
    @classmethod
    def exact_cost(cls, value):
        return exact_money(value) if value is not None else None


class WorkerPayAgreementAction(MoneyCommand):
    expected_agreement_version: int = Field(ge=0)


class WorkerPayAgreementCancel(WorkerPayAgreementAction, WorkerMoneyCorrection):
    pass


class WorkerPayPayoutCreate(MoneyAmountCommand):
    method: Literal["cash", "bank"] = "cash"


class WorkerPayOffsetCreate(MoneyAmountCommand):
    pass


class WorkerPayAgreementItem(BaseModel):
    id: int
    worker_profile_id: int
    order_id: int
    assignment_reference: int
    work_stage_id: int | None
    work_key: str
    title: str
    amount: str
    currency: str
    status: Literal["agreed", "accrued", "cancelled"]
    version: int
    paid: str
    owed: str
    created_at: datetime


class ManagerWorkerPayAgreementItem(WorkerPayAgreementItem):
    cost_byn_amount: str


class WorkerPayBalance(BaseModel):
    currency: str
    agreed: str
    accrued: str
    paid: str
    owed: str


class WorkerPayEntry(BaseModel):
    id: int
    kind: Literal["payout", "offset", "payout_reversal", "offset_reversal"]
    status: Literal["recorded", "reversed"]
    amount: str
    currency: str
    method: Literal["cash", "bank", "offset"]
    created_at: datetime
    version: int
    can_reverse: bool = False


class WorkerPayWorkspace(BaseModel):
    worker_profile_id: int | None
    staff_user_id: int
    display_name: str
    version: int
    can_manage: bool
    can_offset: bool
    balances: list[WorkerPayBalance]
    agreements: list[WorkerPayAgreementItem]
    items: list[WorkerPayEntry]
    total: int
    page: int
    limit: int


class ManagerWorkerPayWorkspace(WorkerPayWorkspace):
    agreements: list[ManagerWorkerPayAgreementItem]


class WorkerPayOverviewItem(BaseModel):
    worker_profile_id: int
    staff_user_id: int
    display_name: str
    balances: list[WorkerPayBalance]


class WorkerPayOverview(BaseModel):
    items: list[WorkerPayOverviewItem]
    total: int
    page: int
    limit: int
    can_manage: bool
    can_offset: bool


class WorkerPayCandidate(BaseModel):
    assignment_id: int
    worker_profile_id: int
    staff_user_id: int
    display_name: str
    title: str
    work_stage_id: int | None
    account_version: int


class WorkerPayOrderWorkspace(BaseModel):
    order_id: int
    candidates: list[WorkerPayCandidate]
    agreements: list[ManagerWorkerPayAgreementItem]
    can_manage: bool
