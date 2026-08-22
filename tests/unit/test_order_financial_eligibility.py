from models import Order, OrderStatus
from services.order_financial_eligibility import is_successful_order


def test_reconciliation_requires_explicit_successful_completion():
    assert is_successful_order(
        Order(status=OrderStatus.CLOSED, closing_result="won")
    ) is True

    for order in (
        Order(status=OrderStatus.CLOSED, closing_result="lost"),
        Order(status=OrderStatus.CLOSED, closing_result=None),
        Order(status=OrderStatus.EXECUTION, closing_result=None),
        Order(
            status=OrderStatus.NEGOTIATION,
            negotiation_status="awaiting_payment",
        ),
    ):
        assert is_successful_order(order) is False
