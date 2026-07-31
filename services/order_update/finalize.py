"""Final invariants and transactional side effects for Manager order updates."""

from sqlalchemy import and_, func, not_, or_
from sqlmodel import select

from models import Customer, Order, OrderStatus
from services.order_service import OrderService
from services.order_update.context import OrderUpdateContext
from services.staff_task_notification_event_service import (
    StaffTaskNotificationEventService,
)
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import tenant_scope_clause


async def finalize_order_update(context: OrderUpdateContext) -> None:
    order = context.order

    transitioned_to_repair = (
        context.previous_workflow_type != "repair"
        and context.current_workflow_type == "repair"
    )
    if transitioned_to_repair and "services" not in context.fields_set:
        await OrderService._maybe_add_default_repair_diagnostic(
            context.session,
            order,
        )

    if order.status == OrderStatus.CLOSED and order.closing_result == "won":
        await context.session.flush()
        await OrderService._refresh_order_financials(context.session, order)
        if order.balance_due > 0:
            raise ValueError(
                f"Cannot close won order with unpaid balance: {order.balance_due}"
            )

    if (
        order.status == OrderStatus.CLOSED
        and order.closing_result == "lost"
        and order.customer_id
    ):
        await _archive_customer_without_other_real_orders(context)

    context.session.add(order)
    await context.session.flush()
    if "customer_delivery_address" in context.fields_set:
        await StaffTaskNotificationEventService.enqueue_address_changes(
            context.session,
            order_id=context.order_id,
            previous_address=context.previous_delivery_address,
            current_address=order.delivery_address,
            tenant_scope=context.tenant_scope,
        )


async def _archive_customer_without_other_real_orders(
    context: OrderUpdateContext,
) -> None:
    order = context.order
    other_real_orders = await context.session.execute(
        select(func.count(Order.id)).where(
            Order.customer_id == order.customer_id,
            Order.id != order.id,
            TenantEntityAccessService.order_clause(context.tenant_scope),
            not_(
                or_(
                    Order.status == OrderStatus.NEW_LEAD,
                    and_(
                        Order.status == OrderStatus.CLOSED,
                        Order.closing_result == "lost",
                    ),
                )
            ),
        )
    )
    if int(other_real_orders.scalar() or 0) != 0:
        return

    customer = (
        await context.session.execute(
            select(Customer).where(
                Customer.id == order.customer_id,
                tenant_scope_clause(Customer, context.tenant_scope),
            )
        )
    ).scalars().first()
    if customer and not customer.is_archived:
        customer.is_archived = True
        context.session.add(customer)
