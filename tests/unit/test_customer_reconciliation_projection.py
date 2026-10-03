from datetime import date, datetime

from models import BankReceipt, Order, OrderDocument, Payment
from models.common import OrderStatus, PaymentCurrency
from services.customer_reconciliation_projection import project


START = datetime(2026, 1, 1)
END = datetime(2026, 12, 31, 23, 59, 59)


def order(order_id: int, *, contract_id: int | None = None, won: bool = True) -> Order:
    item = Order(
        id=order_id, tenant_id=1, storefront_id=1, customer_id=1,
        status=OrderStatus.CLOSED if won else OrderStatus.NEGOTIATION,
        closing_result="won" if won else None,
        customer_contract_id=contract_id, total_amount=1000,
        created_at=datetime(2026, 2, 1),
    )
    item.documents = []
    item.payments = []
    return item


def issued_doc(doc_id: int, *, amount: str, issued_on: date,
               doc_type: str = "act", contract_id: int | None = None,
               status: str = "issued") -> OrderDocument:
    return OrderDocument(
        id=doc_id, order_id=1, doc_type=doc_type, status=status,
        number=f"crm-{doc_id}", date=datetime(2026, 2, 1),
        official_series="A-", official_number=str(doc_id), official_date=issued_on,
        base_customer_contract_id=contract_id,
        render_snapshot={"table_rows": {"lines": [{"line.amount": amount}]}},
    )


def test_partial_issued_amounts_use_frozen_rows_and_official_dates():
    item = order(1)
    item.documents = [
        issued_doc(1, amount="200,00", issued_on=date(2025, 12, 20)),
        issued_doc(2, amount="300,00", issued_on=date(2026, 2, 10)),
    ]
    result = project([item], START, END)
    assert result["opening_balance"] == 200
    assert result["documents_total"] == 300
    assert result["documents"][0]["basis"] == "Акт №A-2"
    assert result["documents"][0]["amount_source"] == "frozen_snapshot"
    assert result["ready_for_generation"] is True


def test_print_variants_count_once_and_repeated_acts_count_twice():
    item = order(1)
    item.documents = [
        issued_doc(1, amount="200,00", issued_on=date(2026, 2, 10)),
        issued_doc(2, amount="200,00", issued_on=date(2026, 2, 10), doc_type="tn2"),
        issued_doc(3, amount="200,00", issued_on=date(2026, 2, 10)),
    ]
    result = project([item], START, END)
    assert result["documents_total"] == 400
    assert len(result["documents"]) == 2
    assert result["ready_for_generation"] is False
    assert any(w["code"] == "possible_duplicate_delivery_event" for w in result["warnings"])


def test_open_order_issued_partial_act_is_debited():
    item = order(1, won=False)
    item.documents = [issued_doc(1, amount="250,00", issued_on=date(2026, 2, 10))]
    result = project([item], START, END)
    assert result["documents_total"] == 250
    assert result["documents"][0]["basis"] == "Акт №A-1"
    assert result["ready_for_generation"] is True


def test_stale_issued_predecessor_is_excluded_when_replacement_issued():
    item = order(1)
    old = issued_doc(1, amount="250,00", issued_on=date(2026, 2, 10))
    replacement = issued_doc(2, amount="300,00", issued_on=date(2026, 2, 11))
    replacement.replaces_document_id = old.id
    item.documents = [old, replacement]
    result = project([item], START, END)
    assert result["documents_total"] == 300
    assert result["documents"][0]["basis"] == "Акт №A-2"


def test_void_and_replaced_documents_are_not_delivery_evidence():
    item = order(1)
    item.documents = [
        issued_doc(1, amount="300,00", issued_on=date(2026, 2, 10), status="void"),
        issued_doc(2, amount="400,00", issued_on=date(2026, 2, 10), status="replaced"),
    ]
    result = project([item], START, END)
    assert result["documents_total"] == 0
    assert result["ready_for_generation"] is False
    assert result["warnings"][0]["code"] == "delivery_document_inactive"


def test_contract_filter_uses_document_association_not_order_default():
    item = order(1, contract_id=7)
    item.documents = [issued_doc(1, amount="250,00", issued_on=date(2026, 2, 10), contract_id=8)]
    assert project([item], START, END, 7)["documents_total"] == 0
    result = project([item], START, END, 8)
    assert result["documents_total"] == 250
    assert result["documents"][0]["contract_id"] == 8


def test_open_order_advance_and_repeated_bank_allocations():
    item = order(1, contract_id=7, won=False)
    receipt = BankReceipt(id=10, amount=300, currency=PaymentCurrency.BYN,
                          status="matched", sender_email="bank@example.com", subject="Payment",
                          fingerprint="bank-10", raw_body="body")
    item.payments = [
        Payment(id=1, order_id=1, bank_receipt_id=10, bank_receipt=receipt,
                amount=100, currency=PaymentCurrency.BYN, date=datetime(2026, 2, 11)),
        Payment(id=2, order_id=1, bank_receipt_id=10, bank_receipt=receipt,
                amount=200, currency=PaymentCurrency.BYN, date=datetime(2026, 2, 11)),
    ]
    result = project([item], START, END, 7)
    assert result["documents_total"] == 0
    assert result["payments_total"] == 300
    assert len(result["payments"]) == 1
    assert result["ready_for_generation"] is True


def test_contract_filter_uses_only_its_share_of_shared_receipt():
    first = order(1, contract_id=7, won=False)
    second = order(2, contract_id=8, won=False)
    receipt = BankReceipt(id=11, amount=300, currency=PaymentCurrency.BYN,
                          status="matched", sender_email="bank@example.com", subject="Shared",
                          fingerprint="bank-11", raw_body="body")
    first.payments = [Payment(id=3, order_id=1, bank_receipt_id=11,
                              bank_receipt=receipt, amount=100,
                              currency=PaymentCurrency.BYN, date=datetime(2026, 2, 11))]
    second.payments = [Payment(id=4, order_id=2, bank_receipt_id=11,
                               bank_receipt=receipt, amount=200,
                               currency=PaymentCurrency.BYN, date=datetime(2026, 2, 11))]
    result = project([first, second], START, END, 7)
    assert result["payments_total"] == 100
    assert len(result["payments"]) == 1
    assert result["ready_for_generation"] is True


def test_unverified_legacy_identity_and_amount_block_generation():
    item = order(1)
    item.documents = [OrderDocument(id=1, order_id=1, doc_type="act", number="135",
                                    date=datetime(2026, 3, 1), google_file_id="original")]
    result = project([item], START, END)
    assert result["documents_total"] == 1000
    assert result["documents"][0]["amount_source"] == "order_total_unverified"
    assert result["ready_for_generation"] is False
    assert any(w["code"] == "document_source_unverified" for w in result["warnings"])
    assert any(w["can_review_legacy"] for w in result["warnings"])
