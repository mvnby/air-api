"""Commercial line reconciliation for Manager order updates."""

from sqlalchemy import delete
from sqlmodel import select

from models import OrderServiceLink, Product, Service
from services.order_product_line_service import OrderProductLineService
from services.order_proposal_lifecycle import (
    PROPOSAL_STATUS_APPROVED,
    PROPOSAL_STATUS_SENT,
    normalize_proposal_status,
)
from services.order_service import OrderService
from services.order_update.context import OrderUpdateContext


async def apply_commercial_lines(context: OrderUpdateContext) -> None:
    if "products" not in context.fields_set and "services" not in context.fields_set:
        if context.currency_fields_changed:
            await context.session.flush()
            await OrderService._refresh_order_financials(
                context.session,
                context.order,
            )
        else:
            OrderService._apply_payment_state(context.order)
        return

    await context.session.refresh(
        context.order,
        attribute_names=[
            "proposals",
            "product_links",
            "service_links",
            "payments",
            "installers",
        ],
    )
    selected_proposal = await OrderService.ensure_default_proposal(
        context.session,
        context.order,
    )
    target_proposal_id = _resolve_target_proposal_id(context, selected_proposal.id)
    target_proposal = next(
        (
            proposal
            for proposal in context.order.proposals
            if proposal.id == target_proposal_id and not proposal.is_archived
        ),
        None,
    )
    if not target_proposal:
        raise ValueError("Proposal not found")
    if normalize_proposal_status(target_proposal.status) in {
        PROPOSAL_STATUS_SENT,
        PROPOSAL_STATUS_APPROVED,
    }:
        raise ValueError(
            "Sent or accepted proposal cannot be edited. "
            "Return it to draft or create a copy"
        )

    if "products" in context.fields_set and context.payload.products is not None:
        await _replace_product_lines(context, target_proposal_id)
    if "services" in context.fields_set and context.payload.services is not None:
        await _replace_service_lines(context, target_proposal_id)

    await context.session.flush()
    await OrderService._refresh_order_financials(
        context.session,
        context.order,
    )


def _resolve_target_proposal_id(
    context: OrderUpdateContext,
    default_proposal_id: int,
) -> int:
    payload_proposal_ids = {
        int(line.proposal_id)
        for line in list(context.payload.products or [])
        + list(context.payload.services or [])
        if getattr(line, "proposal_id", None)
    }
    if len(payload_proposal_ids) > 1:
        raise ValueError("Only one proposal can be updated at a time")
    return next(iter(payload_proposal_ids), None) or int(default_proposal_id)


async def _replace_product_lines(
    context: OrderUpdateContext,
    proposal_id: int,
) -> None:
    product_lines = list(context.payload.products)
    for line in product_lines:
        if line.quantity <= 0:
            raise ValueError("Product quantity must be > 0")
        if line.price < 0:
            raise ValueError("Product price cannot be negative")
        if line.cost is not None and line.cost < 0:
            raise ValueError("Product cost cannot be negative")

    product_ids = {int(line.product_id) for line in product_lines}
    if product_ids:
        result = await context.session.execute(
            select(Product.id).where(Product.id.in_(product_ids))
        )
        existing_product_ids = {int(product_id) for product_id in result.scalars()}
        missing_product_ids = sorted(product_ids - existing_product_ids)
        if missing_product_ids:
            raise ValueError(f"Product not found: {missing_product_ids[0]}")

    cost_defaults = await OrderService._build_product_line_cost_defaults(
        context.session,
        product_lines,
    )
    values = []
    for line in product_lines:
        logistics_components = OrderService._serialize_order_logistics_components(
            line.logistics_components
        )
        await OrderService._backfill_product_logistics_template(
            context.session,
            line.product_id,
            logistics_components,
        )
        values.append(
            {
                "link_id": line.link_id,
                "product_id": line.product_id,
                "quantity": line.quantity,
                "price": line.price,
                "cost": (
                    line.cost
                    if line.cost is not None
                    else cost_defaults.get(int(line.product_id), 0)
                ),
                "logistics_components": logistics_components,
            }
        )
    await OrderProductLineService.reconcile(
        context.session,
        order_id=context.order_id,
        proposal_id=proposal_id,
        lines=values,
    )


async def _replace_service_lines(
    context: OrderUpdateContext,
    proposal_id: int,
) -> None:
    service_lines = list(context.payload.services)
    for line in service_lines:
        if line.quantity <= 0:
            raise ValueError("Service quantity must be > 0")
        if line.price < 0:
            raise ValueError("Service price cannot be negative")
        if line.cost is not None and line.cost < 0:
            raise ValueError("Service cost cannot be negative")
        if not line.title:
            raise ValueError("Service title is required")

    service_ids = {
        int(line.service_id)
        for line in service_lines
        if line.service_id is not None
    }
    if service_ids:
        result = await context.session.execute(
            select(Service.id).where(Service.id.in_(service_ids))
        )
        existing_service_ids = {int(service_id) for service_id in result.scalars()}
        missing_service_ids = sorted(service_ids - existing_service_ids)
        if missing_service_ids:
            raise ValueError(f"Service not found: {missing_service_ids[0]}")

    cost_defaults = await OrderService._build_service_line_cost_defaults(
        context.session,
        service_lines,
    )
    await context.session.execute(
        delete(OrderServiceLink).where(
            OrderServiceLink.order_id == context.order_id,
            OrderServiceLink.proposal_id == proposal_id,
        )
    )
    for line in service_lines:
        context.session.add(
            OrderServiceLink(
                order_id=context.order_id,
                proposal_id=proposal_id,
                service_id=line.service_id,
                title=line.title,
                quantity=line.quantity,
                price=line.price,
                cost=(
                    line.cost
                    if line.cost is not None
                    else cost_defaults.get(int(line.service_id), 0)
                    if line.service_id is not None
                    else 0
                ),
            )
        )
