from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from modules.documents.domain import (
    ActTerms,
    B2C_NATIVE_DOCUMENT_TYPES,
    BUSINESS_TERMS_DOCUMENT_TYPES,
    BusinessDocumentTerms,
    CONTRACT_SCENARIOS,
    PAYMENT_DAY_KINDS,
    PaymentScheduleItem,
    PAYMENT_DUE_EVENTS,
)


class BusinessDocumentContextError(ValueError):
    pass


def with_default_goods_warranty(
    terms: BusinessDocumentTerms | None,
    *,
    configured_months: object,
) -> BusinessDocumentTerms | None:
    """Resolve the server-side equipment warranty for supply scenarios."""

    if (
        terms is None
        or terms.contract_scenario not in {"supply", "supply_installation"}
        or terms.goods_warranty_months is not None
    ):
        return terms
    raw_configured = str(configured_months or "").strip()
    try:
        configured = int(raw_configured) if raw_configured else 36
    except ValueError:
        configured = 36
    if configured == 0:
        return replace(terms, goods_warranty_months=0)
    if not 1 <= configured <= 240:
        configured = 36
    return replace(terms, goods_warranty_months=configured)


@dataclass(frozen=True, slots=True)
class BusinessDocumentContext:
    values: dict[str, str]
    conditions: dict[str, bool]
    table_rows: dict[str, list[dict[str, str]]]


_SCENARIO_LABELS = {
    "services": "Оказание услуг",
    "repair": "Диагностика и ремонт",
    "maintenance": "Техническое обслуживание",
    "supply_installation": "Поставка с монтажом",
    "installation": "Монтаж",
    "framework": "Рамочный договор",
    "supply": "Поставка оборудования",
}
_PAYMENT_EVENT_LABELS = {
    "before_supply": "до поставки",
    "before_work": "до начала работ",
    "after_supply": "после поставки",
    "after_work": "после выполнения работ",
    "after_acceptance": "после приемки",
}


def build_business_document_context(
    *,
    document_type: str,
    terms: BusinessDocumentTerms | None,
    act_terms: ActTerms | None,
    order_additional_conditions: str | None,
    total_amount: Decimal,
) -> BusinessDocumentContext:
    if document_type in B2C_NATIVE_DOCUMENT_TYPES:
        if terms is not None or act_terms is not None:
            raise BusinessDocumentContextError(
                "Параметры B2B нельзя передать для B2C заказ-акта"
            )
        return BusinessDocumentContext({}, {}, {})
    if terms is not None and document_type not in BUSINESS_TERMS_DOCUMENT_TYPES:
        raise BusinessDocumentContextError(
            "Параметры B2B доступны только для договора, счета, предложения или акта"
        )
    if document_type not in BUSINESS_TERMS_DOCUMENT_TYPES:
        return BusinessDocumentContext({}, {}, {})
    if document_type == "contract":
        if terms is None or terms.contract_scenario not in CONTRACT_SCENARIOS:
            raise BusinessDocumentContextError("Для договора выберите сценарий")
        if terms.contract_scenario == "framework" and terms.valid_until is None:
            raise BusinessDocumentContextError(
                "Для рамочного договора укажите срок действия"
            )
        if not terms.payment_schedule:
            raise BusinessDocumentContextError("Для договора укажите график оплаты")
    elif terms is not None and terms.contract_scenario is not None:
        raise BusinessDocumentContextError(
            "Сценарий договора можно указать только для договора"
        )
    if act_terms is not None and document_type != "act":
        raise BusinessDocumentContextError("Параметры акта доступны только для акта")
    if document_type == "act" and act_terms is None:
        raise BusinessDocumentContextError(
            "Для акта явно укажите наличие или отсутствие замечаний"
        )

    resolved_terms = _without_disabled_warranties(terms or BusinessDocumentTerms())
    is_act = document_type == "act"
    resolved_act = act_terms or ActTerms()
    _validate_warranty(resolved_terms)
    _validate_schedule(resolved_terms.payment_schedule)
    if is_act:
        _validate_act_terms(resolved_act)
    additional_conditions = _additional_conditions(
        resolved_terms, order_additional_conditions
    )
    payment_amounts = _payment_amounts(
        resolved_terms.payment_schedule,
        total_amount,
    )
    schedule_rows = _payment_rows(
        resolved_terms.payment_schedule,
        payment_amounts,
    )
    scenario = resolved_terms.contract_scenario or ""
    goods_warranty_present = resolved_terms.goods_warranty_months is not None
    work_warranty_present = resolved_terms.work_warranty_months is not None
    return BusinessDocumentContext(
        values={
            "contract.scenario": scenario,
            "contract.scenario_label": _SCENARIO_LABELS.get(scenario, ""),
            "contract.subject": _text(resolved_terms.subject),
            "contract.valid_until": _date(resolved_terms.valid_until),
            "contract.delivery_deadline": _date(resolved_terms.delivery_deadline),
            "contract.performance_deadline": _date(resolved_terms.performance_deadline),
            "contract.additional_conditions": additional_conditions,
            "payment.summary": _payment_summary(resolved_terms.payment_schedule),
            "payment.total": _money(total_amount),
            "payment.prepayment_amount": _prepayment_amount(
                resolved_terms.payment_schedule, payment_amounts
            ),
            "payment.balance_amount": _balance_amount(
                resolved_terms.payment_schedule, payment_amounts
            ),
            "payment.currency": "BYN",
            "warranty.goods.months": _months(resolved_terms.goods_warranty_months),
            "warranty.goods.terms": _text(resolved_terms.goods_warranty_terms),
            "warranty.work.months": _months(resolved_terms.work_warranty_months),
            "warranty.work.terms": _text(resolved_terms.work_warranty_terms),
            "act.result_text": _text(resolved_act.result_text) if is_act else "",
            "act.claims_text": _text(resolved_act.claims_text) if is_act else "",
            "act.acceptance_deadline": (
                _date(resolved_act.acceptance_deadline) if is_act else ""
            ),
        },
        conditions={
            **{
                f"contract.is_{candidate}": scenario == candidate
                for candidate in CONTRACT_SCENARIOS
            },
            "contract.framework": scenario == "framework",
            "contract.has_subject": bool(_text(resolved_terms.subject)),
            "contract.has_additional_conditions": bool(additional_conditions),
            "contract.has_delivery_deadline": resolved_terms.delivery_deadline
            is not None,
            "contract.has_no_delivery_deadline": resolved_terms.delivery_deadline
            is None,
            "contract.has_performance_deadline": resolved_terms.performance_deadline
            is not None,
            "contract.has_no_performance_deadline": (
                resolved_terms.performance_deadline is None
            ),
            "contract.has_any_deadline": (
                resolved_terms.delivery_deadline is not None
                or resolved_terms.performance_deadline is not None
            ),
            "contract.has_no_deadlines": (
                resolved_terms.delivery_deadline is None
                and resolved_terms.performance_deadline is None
            ),
            "payment.has_schedule": bool(schedule_rows),
            "payment.is_full_prepayment": _is_full_prepayment(
                resolved_terms.payment_schedule
            ),
            "payment.is_equipment_prepayment_balance": _is_equipment_prepayment_balance(
                resolved_terms.payment_schedule
            ),
            "payment.is_postpayment": _is_postpayment(resolved_terms.payment_schedule),
            "payment.is_custom_schedule": bool(schedule_rows)
            and not _is_full_prepayment(resolved_terms.payment_schedule)
            and not _is_equipment_prepayment_balance(resolved_terms.payment_schedule)
            and not _is_postpayment(resolved_terms.payment_schedule),
            "warranty.goods.present": goods_warranty_present,
            "warranty.work.present": work_warranty_present,
            "warranty.any_present": (
                goods_warranty_present or work_warranty_present
            ),
            "act.claims_present": is_act and resolved_act.claims_status == "present",
            "act.no_claims": is_act and resolved_act.claims_status == "none",
            "act.has_result": is_act and bool(_text(resolved_act.result_text)),
            "act.has_acceptance_deadline": (
                is_act and resolved_act.acceptance_deadline is not None
            ),
        },
        table_rows={"payment_schedule": schedule_rows},
    )


def _without_disabled_warranties(terms: BusinessDocumentTerms) -> BusinessDocumentTerms:
    changes: dict[str, object] = {}
    if terms.goods_warranty_months == 0:
        changes.update(goods_warranty_months=None, goods_warranty_terms=None)
    if terms.work_warranty_months == 0:
        changes.update(work_warranty_months=None, work_warranty_terms=None)
    return replace(terms, **changes) if changes else terms


def _validate_warranty(terms: BusinessDocumentTerms) -> None:
    for label, months in (
        ("оборудование", terms.goods_warranty_months),
        ("работы", terms.work_warranty_months),
    ):
        if months is not None and not 1 <= months <= 240:
            raise BusinessDocumentContextError(
                f"Срок гарантии на {label} должен быть от 1 до 240 месяцев"
            )
    if terms.goods_warranty_months is None and _text(terms.goods_warranty_terms):
        raise BusinessDocumentContextError(
            "Условия гарантии на оборудование указываются вместе со сроком"
        )
    if terms.work_warranty_months is None and _text(terms.work_warranty_terms):
        raise BusinessDocumentContextError(
            "Условия гарантии на работы указываются вместе со сроком"
        )


def _validate_schedule(schedule: tuple[PaymentScheduleItem, ...]) -> None:
    if not schedule:
        return
    if sum((item.share_percent for item in schedule), Decimal("0")) != Decimal("100"):
        raise BusinessDocumentContextError("График оплаты должен составлять ровно 100%")
    for item in schedule:
        if item.share_percent <= 0 or item.share_percent > 100:
            raise BusinessDocumentContextError("Доля платежа должна быть от 0 до 100%")
        if item.due_event not in PAYMENT_DUE_EVENTS:
            raise BusinessDocumentContextError("Неизвестный срок оплаты")
        if item.due_day_kind not in PAYMENT_DAY_KINDS:
            raise BusinessDocumentContextError("Неизвестный вид дней для срока оплаты")
        if item.due_days is not None and not 1 <= item.due_days <= 3650:
            raise BusinessDocumentContextError(
                "Количество дней для оплаты должно быть от 1 до 3650"
            )


def _validate_act_terms(terms: ActTerms) -> None:
    if terms.claims_status not in {"none", "present"}:
        raise BusinessDocumentContextError("Неизвестный статус замечаний к акту")
    if terms.claims_status == "present" and not _text(terms.claims_text):
        raise BusinessDocumentContextError("При наличии замечаний укажите их текст")


def _additional_conditions(
    terms: BusinessDocumentTerms, order_value: str | None
) -> str:
    if terms.additional_conditions_overridden:
        return _text(terms.additional_conditions)
    return _text(order_value)


def _payment_rows(
    schedule: tuple[PaymentScheduleItem, ...], amounts: tuple[Decimal, ...]
) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for number, (item, amount) in enumerate(zip(schedule, amounts), start=1):
        rows.append(
            {
                "payment.number": str(number),
                "payment.share_percent": f"{item.share_percent.normalize():f}",
                "payment.amount": _money(amount),
                "payment.due_event": _payment_due_label(item),
                "payment.due_days": str(item.due_days or ""),
                "payment.due_day_kind": _payment_day_kind_label(item.due_day_kind),
                "payment.note": _text(item.note),
            }
        )
    return rows


def _payment_amounts(
    schedule: tuple[PaymentScheduleItem, ...], total: Decimal
) -> tuple[Decimal, ...]:
    if not schedule:
        return ()
    rounded_total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    allocated = Decimal("0")
    amounts: list[Decimal] = []
    for index, item in enumerate(schedule):
        if index == len(schedule) - 1:
            amount = rounded_total - allocated
        else:
            amount = (rounded_total * item.share_percent / Decimal("100")).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
            allocated += amount
        amounts.append(amount)
    return tuple(amounts)


def _payment_summary(schedule: tuple[PaymentScheduleItem, ...]) -> str:
    if not schedule:
        return ""
    return "; ".join(
        f"{item.share_percent.normalize():f}% {_payment_due_label(item)}"
        for item in schedule
    )


def _prepayment_amount(
    schedule: tuple[PaymentScheduleItem, ...], amounts: tuple[Decimal, ...]
) -> str:
    amount = sum(
        (
            item_amount
            for item, item_amount in zip(schedule, amounts)
            if item.due_event.startswith("before_")
        ),
        Decimal("0"),
    )
    return _money(amount) if amount else ""


def _balance_amount(
    schedule: tuple[PaymentScheduleItem, ...], amounts: tuple[Decimal, ...]
) -> str:
    if not schedule:
        return ""
    amount = sum(
        (
            item_amount
            for item, item_amount in zip(schedule, amounts)
            if not item.due_event.startswith("before_")
        ),
        Decimal("0"),
    )
    return _money(amount)


def _is_full_prepayment(schedule: tuple[PaymentScheduleItem, ...]) -> bool:
    return (
        len(schedule) == 1
        and schedule[0].share_percent == Decimal("100")
        and schedule[0].due_event.startswith("before_")
    )


def _is_equipment_prepayment_balance(schedule: tuple[PaymentScheduleItem, ...]) -> bool:
    return (
        len(schedule) == 2
        and schedule[0].due_event == "before_supply"
        and schedule[1].due_event in {"after_work", "after_acceptance"}
    )


def _is_postpayment(schedule: tuple[PaymentScheduleItem, ...]) -> bool:
    return len(schedule) == 1 and schedule[0].due_event in {
        "after_supply",
        "after_work",
        "after_acceptance",
    }


def _payment_due_label(item: PaymentScheduleItem) -> str:
    event = _PAYMENT_EVENT_LABELS[item.due_event]
    if item.due_days is None:
        return event
    days = _payment_days_phrase(item.due_days, item.due_day_kind)
    if item.due_event.startswith("before_"):
        return f"не позднее чем за {days} до {event.removeprefix('до ')}"
    return f"в течение {days} {event}"


def _payment_day_kind_label(value: str) -> str:
    return "банковские дни" if value == "banking" else "календарные дни"


def _payment_days_phrase(value: int, kind: str) -> str:
    remainder_100 = value % 100
    remainder_10 = value % 10
    if remainder_10 == 1 and remainder_100 != 11:
        noun = "банковский день" if kind == "banking" else "календарный день"
    elif 2 <= remainder_10 <= 4 and not 12 <= remainder_100 <= 14:
        noun = "банковских дня" if kind == "banking" else "календарных дня"
    else:
        noun = "банковских дней" if kind == "banking" else "календарных дней"
    return f"{value} {noun}"


def _text(value: object | None) -> str:
    return str(value or "").strip()


def _date(value: date | None) -> str:
    return value.strftime("%d.%m.%Y") if value is not None else ""


def _months(value: int | None) -> str:
    return str(value) if value is not None else ""


def _money(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):.2f}"
