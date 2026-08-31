from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal


CONTRACT_SCENARIOS = frozenset(
    {
        "services",
        "repair",
        "maintenance",
        "supply_installation",
        "installation",
        "framework",
        "supply",
    }
)

BUSINESS_TERMS_DOCUMENT_TYPES = frozenset({"contract", "offer", "invoice", "act"})

PAYMENT_DUE_EVENTS = frozenset(
    {
        "before_supply",
        "before_work",
        "after_supply",
        "after_work",
        "after_acceptance",
    }
)

PAYMENT_DAY_KINDS = frozenset({"calendar", "banking"})


@dataclass(frozen=True, slots=True)
class PaymentScheduleItem:
    share_percent: Decimal
    due_event: str
    due_days: int | None = None
    due_day_kind: str = "calendar"
    note: str | None = None


@dataclass(frozen=True, slots=True)
class BusinessDocumentTerms:
    contract_scenario: str | None = None
    subject: str | None = None
    delivery_deadline: date | None = None
    performance_deadline: date | None = None
    valid_until: date | None = None
    additional_conditions: str | None = None
    additional_conditions_overridden: bool = False
    payment_schedule: tuple[PaymentScheduleItem, ...] = ()
    goods_warranty_months: int | None = None
    goods_warranty_terms: str | None = None
    work_warranty_months: int | None = None
    work_warranty_terms: str | None = None


@dataclass(frozen=True, slots=True)
class ActTerms:
    result_text: str | None = None
    claims_status: str = "none"
    claims_text: str | None = None
    acceptance_deadline: date | None = None
