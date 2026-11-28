"""Payment history and manual receipt registration in the Telegram order desk."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints


BotPaymentCurrency = Literal["BYN", "USD", "EUR"]
BotPaymentType = Literal["prepayment", "postpayment"]


class BotOrderPayment(BaseModel):
    id: int
    amount: Decimal
    currency: BotPaymentCurrency
    type: BotPaymentType
    received_on: date
    comment: str | None
    bank_confirmed: bool


class BotOrderPayments(BaseModel):
    total_amount: Decimal
    total_payments: Decimal
    balance_due: Decimal
    entries: list[BotOrderPayment] = Field(default_factory=list)
    currencies: list[BotPaymentCurrency] = Field(default_factory=list)
    target_currency: Literal["USD", "EUR"] | None = None
    target_currency_amount: Decimal | None = None
    target_currency_payments: Decimal | None = None
    target_currency_balance_due: Decimal | None = None
    exchange_rate: Decimal | None = None
    received_on_max: date
    can_record: bool = False
    record_unavailable_reason: str | None = None
    workflow_notice: str | None = None


class BotRecordPayment(BaseModel, extra="forbid"):
    kind: Literal["record_payment"]
    amount: Decimal = Field(gt=0, max_digits=15, decimal_places=2)
    currency: BotPaymentCurrency
    type: BotPaymentType
    received_on: date
    comment: Annotated[str, StringConstraints(strip_whitespace=True, max_length=500)] | None = None
    confirmed: Annotated[bool, Field(strict=True)] = False
