from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest

from modules.documents.application.business_context import (
    build_business_document_context,
)
from modules.documents.application.draft_parameters import read_draft_parameters
from modules.documents.domain import BusinessDocumentTerms, PaymentScheduleItem


@pytest.mark.parametrize(
    "event",
    ["before_supply", "before_work", "after_supply", "after_work", "after_acceptance"],
)
@pytest.mark.parametrize("day_kind", ["calendar", "banking", "working"])
def test_existing_drafts_recover_exact_payment_terms_without_reading_crm(
    event, day_kind
):
    context = build_business_document_context(
        document_type="contract",
        terms=BusinessDocumentTerms(
            contract_scenario="services",
            subject="Согласованные работы",
            performance_deadline=date(2026, 10, 15),
            payment_schedule=(
                PaymentScheduleItem(
                    Decimal("100"),
                    event,
                    due_days=3,
                    due_day_kind=day_kind,
                    note="До подписания",
                ),
            ),
        ),
        act_terms=None,
        order_additional_conditions="Сохранённые условия заказа",
        total_amount=Decimal("1000"),
    )
    document = SimpleNamespace(
        doc_type="contract",
        date=datetime(2026, 10, 9),
        render_snapshot={
            "values": context.values,
            "conditions": context.conditions,
            "table_rows": context.table_rows,
            "meta": {},
        },
    )
    parameters = read_draft_parameters(document)
    business = parameters["business_terms"]
    assert parameters["issue_date"] == "2026-10-09"
    assert business["subject"] == "Согласованные работы"
    assert business["performance_deadline"] == "2026-10-15"
    assert business["additional_conditions"] == "Сохранённые условия заказа"
    assert business["payment_schedule"] == [
        {
            "share_percent": "100",
            "due_event": event,
            "due_days": 3,
            "due_day_kind": day_kind,
            "note": "До подписания",
        }
    ]
