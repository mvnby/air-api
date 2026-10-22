"""Payment may fund a planned first visit, but cannot finish a waiting/future visit."""

import pytest
from models import Order, OrderWorkStage
from services.order_service import OrderService


@pytest.mark.parametrize("held", [True, False])
@pytest.mark.parametrize("status", ["negotiation", "execution"])
@pytest.mark.parametrize(
    "stage", [None, "planned", "in_progress", "completed", "canceled"]
)
def test_full_payment_transitions_respect_waiting_and_actual_work(held, status, stage):
    order = Order(
        status=status,
        is_on_hold=held,
        total_amount=1000,
        balance_due=0,
        auto_execution_on_payment=True,
        auto_close_on_payment=True,
        execution_status="awaiting_payment",
    )
    order.work_stages = (
        [] if stage is None else [OrderWorkStage(name="Visit", status=stage)]
    )
    OrderService._apply_payment_state(order)
    assert order.is_paid
    if held:
        assert order.status == status and order.closing_result is None
    elif stage in {"planned", "in_progress", "canceled"}:
        assert order.status == "execution" and order.closing_result is None
    else:
        assert order.status == "closed" and order.closing_result == "won"
