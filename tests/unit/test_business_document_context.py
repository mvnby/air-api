from datetime import date
from decimal import Decimal

import pytest

from modules.documents.api.schemas import ManagedDocumentDraftPayload

from modules.documents.application.business_context import (
    BusinessDocumentContextError,
    build_business_document_context,
)
from modules.documents.domain import (
    ActTerms,
    BusinessDocumentTerms,
    PaymentScheduleItem,
)


def _terms(**changes) -> BusinessDocumentTerms:
    values = {
        "contract_scenario": "supply_installation",
        "payment_schedule": (
            PaymentScheduleItem(Decimal("60"), "before_supply"),
            PaymentScheduleItem(Decimal("40"), "after_work"),
        ),
    }
    values.update(changes)
    return BusinessDocumentTerms(**values)


def test_business_context_snapshots_schedule_conditions_and_explicit_conditions():
    context = build_business_document_context(
        document_type="contract",
        terms=_terms(
            additional_conditions="Оплата в течение пяти дней после подписания акта",
            additional_conditions_overridden=True,
            goods_warranty_months=24,
            goods_warranty_terms="По условиям поставщика",
            work_warranty_months=12,
            work_warranty_terms="При соблюдении правил эксплуатации",
            delivery_deadline=date(2026, 9, 15),
        ),
        act_terms=None,
        order_additional_conditions="Старые условия заказа",
        total_amount=Decimal("1000"),
    )

    assert context.values["contract.additional_conditions"].startswith("Оплата")
    assert context.values["warranty.goods.months"] == "24"
    assert context.values["warranty.work.months"] == "12"
    assert context.conditions["contract.is_supply_installation"] is True
    assert context.conditions["payment.is_equipment_prepayment_balance"] is True
    assert context.conditions["warranty.goods.present"] is True
    assert context.conditions["warranty.any_present"] is True
    assert context.table_rows["payment_schedule"] == [
        {
            "payment.number": "1",
            "payment.share_percent": "60",
            "payment.amount": "600.00",
            "payment.due_event": "до поставки",
            "payment.due_days": "",
            "payment.due_day_kind": "календарные дни",
            "payment.note": "",
        },
        {
            "payment.number": "2",
            "payment.share_percent": "40",
            "payment.amount": "400.00",
            "payment.due_event": "после выполнения работ",
            "payment.due_days": "",
            "payment.due_day_kind": "календарные дни",
            "payment.note": "",
        },
    ]


def test_business_context_uses_order_conditions_only_without_explicit_override():
    context = build_business_document_context(
        document_type="contract",
        terms=_terms(),
        act_terms=None,
        order_additional_conditions="Условие из заказа",
        total_amount=Decimal("1"),
    )

    assert context.values["contract.additional_conditions"] == "Условие из заказа"


def test_payment_deadline_keeps_event_day_count_and_day_kind():
    context = build_business_document_context(
        document_type="invoice",
        terms=BusinessDocumentTerms(
            payment_schedule=(
                PaymentScheduleItem(
                    Decimal("100"),
                    "after_acceptance",
                    due_days=5,
                    due_day_kind="banking",
                ),
            )
        ),
        act_terms=None,
        order_additional_conditions=None,
        total_amount=Decimal("250"),
    )

    assert context.values["payment.summary"] == (
        "100% в течение 5 банковских дней после приемки"
    )
    assert context.table_rows["payment_schedule"][0]["payment.due_day_kind"] == (
        "банковские дни"
    )


def test_payment_rounding_residual_is_assigned_to_the_final_stage():
    context = build_business_document_context(
        document_type="contract",
        terms=_terms(
            payment_schedule=(
                PaymentScheduleItem(Decimal("50"), "before_supply"),
                PaymentScheduleItem(Decimal("50"), "after_work"),
            )
        ),
        act_terms=None,
        order_additional_conditions=None,
        total_amount=Decimal("100.01"),
    )

    amounts = [
        Decimal(row["payment.amount"])
        for row in context.table_rows["payment_schedule"]
    ]
    assert amounts == [Decimal("50.01"), Decimal("50.00")]
    assert sum(amounts) == Decimal(context.values["payment.total"])
    assert context.values["payment.prepayment_amount"] == "50.01"
    assert context.values["payment.balance_amount"] == "50.00"


def test_business_context_rejects_framework_without_valid_until_and_warranty_text_without_months():
    with pytest.raises(BusinessDocumentContextError, match="срок действия"):
        build_business_document_context(
            document_type="contract",
            terms=BusinessDocumentTerms(contract_scenario="framework"),
            act_terms=None,
            order_additional_conditions=None,
            total_amount=Decimal("0"),
        )
    with pytest.raises(BusinessDocumentContextError, match="оборудование"):
        build_business_document_context(
            document_type="contract",
            terms=_terms(goods_warranty_terms="Без срока"),
            act_terms=None,
            order_additional_conditions=None,
            total_amount=Decimal("1"),
        )
    with pytest.raises(BusinessDocumentContextError, match="от 1 до 240"):
        build_business_document_context(
            document_type="contract",
            terms=_terms(goods_warranty_months=0),
            act_terms=None,
            order_additional_conditions=None,
            total_amount=Decimal("1"),
        )


def test_act_terms_are_only_available_for_b2b_act():
    context = build_business_document_context(
        document_type="act",
        terms=None,
        act_terms=ActTerms(
            result_text="Работы выполнены полностью",
            claims_status="present",
            claims_text="Подписать после устранения замечаний",
            acceptance_deadline=date(2026, 9, 5),
        ),
        order_additional_conditions=None,
        total_amount=Decimal("0"),
    )

    assert context.conditions["act.claims_present"] is True
    assert context.values["act.acceptance_deadline"] == "05.09.2026"
    with pytest.raises(BusinessDocumentContextError, match="только для акта"):
        build_business_document_context(
            document_type="offer",
            terms=None,
            act_terms=ActTerms(),
            order_additional_conditions=None,
            total_amount=Decimal("0"),
        )
    with pytest.raises(BusinessDocumentContextError, match="явно укажите"):
        build_business_document_context(
            document_type="act",
            terms=None,
            act_terms=None,
            order_additional_conditions=None,
            total_amount=Decimal("0"),
        )
    with pytest.raises(ValueError, match="явно укажите"):
        ManagedDocumentDraftPayload(
            legal_entity_id=1,
            document_type="act",
            issue_date=date(2026, 8, 31),
        )


def test_non_act_business_document_does_not_claim_that_customer_has_no_claims():
    context = build_business_document_context(
        document_type="invoice",
        terms=BusinessDocumentTerms(),
        act_terms=None,
        order_additional_conditions=None,
        total_amount=Decimal("100"),
    )

    assert context.conditions["act.no_claims"] is False
    assert context.values["payment.balance_amount"] == ""


def test_business_terms_are_rejected_for_transport_documents():
    with pytest.raises(BusinessDocumentContextError, match="доступны только"):
        build_business_document_context(
            document_type="tn2",
            terms=BusinessDocumentTerms(),
            act_terms=None,
            order_additional_conditions=None,
            total_amount=Decimal("100"),
        )

    with pytest.raises(ValueError, match="доступны только"):
        ManagedDocumentDraftPayload(
            legal_entity_id=1,
            document_type="ttn1",
            issue_date=date(2026, 8, 31),
            business_terms={},
        )


def test_contract_payload_requires_scenario_and_a_complete_payment_schedule():
    with pytest.raises(ValueError, match="выберите сценарий"):
        ManagedDocumentDraftPayload(
            legal_entity_id=1,
            document_type="contract",
            issue_date=date(2026, 8, 31),
        )
    with pytest.raises(ValueError, match="укажите график оплаты"):
        ManagedDocumentDraftPayload(
            legal_entity_id=1,
            document_type="contract",
            issue_date=date(2026, 8, 31),
            business_terms={"contract_scenario": "services"},
        )
    with pytest.raises(BusinessDocumentContextError, match="укажите график оплаты"):
        build_business_document_context(
            document_type="contract",
            terms=BusinessDocumentTerms(contract_scenario="services"),
            act_terms=None,
            order_additional_conditions=None,
            total_amount=Decimal("1"),
        )
    with pytest.raises(ValueError, match="ровно 100%"):
        ManagedDocumentDraftPayload(
            legal_entity_id=1,
            document_type="contract",
            issue_date=date(2026, 8, 31),
            business_terms={
                "contract_scenario": "services",
                "payment_schedule": [{"share_percent": 80, "due_event": "before_work"}],
            },
        )
