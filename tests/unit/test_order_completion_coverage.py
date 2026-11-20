"""Completion usage includes prior acts and in-flight number reservations."""

from decimal import Decimal

import pytest

from models import OrderDocument
from modules.documents.application.errors import ManagedDocumentConflictError
from modules.documents.application.order_completion_coverage import (
    COVERAGE_KEY, LineUse, combined_usage, verify_capacity,
)


LINE = ("service", 1)
SECOND = ("service", 2)


def act(row_id, status, lines, *, replaces=None):
    return OrderDocument(
        id=row_id, order_id=1, number=str(row_id), doc_type="act", status=status,
        replaces_document_id=replaces,
        render_snapshot={"meta": {COVERAGE_KEY: {
            "lines": [
                {"kind": key[0], "line_id": key[1], "unit_price": str(price), "quantity": quantity}
                for key, quantity, price in lines
            ],
        }}},
    )


def test_pending_replacement_holds_both_old_and_new_lines_without_counting_overlap_twice():
    original = act(1, "issued", [(LINE, 2, 60)])
    replacement = act(2, "draft", [(LINE, 1, 70), (SECOND, 1, 30)], replaces=1)
    independent = act(3, "signed", [(LINE, 1, 50)])
    usage = combined_usage([original, replacement, independent])
    assert usage == {LINE: LineUse(3, Decimal(170)), SECOND: LineUse(1, Decimal(30))}

    # Only release the old allocation once issuance changes the active document.
    replacement.status = "issued"
    usage = combined_usage([replacement, independent])
    assert usage == {LINE: LineUse(2, Decimal(120)), SECOND: LineUse(1, Decimal(30))}


def test_remaining_value_is_checked_even_when_remaining_quantity_allows_new_act():
    prior = {LINE: LineUse(1, Decimal(120))}
    limits = {LINE: LineUse(2, Decimal(200))}
    verify_capacity({LINE: LineUse(1, Decimal(80))}, prior, limits)
    with pytest.raises(ManagedDocumentConflictError, match="количество или сумму"):
        verify_capacity({LINE: LineUse(1, Decimal(100))}, prior, limits)
    with pytest.raises(ManagedDocumentConflictError, match="количество или сумму"):
        verify_capacity({LINE: LineUse(2, Decimal(80))}, prior, limits)


def test_printed_legacy_description_cannot_authorize_new_quantities():
    old = OrderDocument(
        id=1, order_id=1, doc_type="act", number="Legacy",
        render_snapshot={"table_rows": {"lines": [{"line.title": "Работы", "line.quantity": "1"}]}},
    )
    with pytest.raises(ManagedDocumentConflictError, match="нет проверяемой разбивки"):
        combined_usage([old])
