"""Tenant-scoped proposal lines, using the Manager commercial command rules."""

from decimal import Decimal

from fastapi import HTTPException
from sqlalchemy.orm import selectinload

from core.config import settings
from models import Order, OrderProductLink, OrderServiceLink
from schemas_connector_service_order_lines import ServiceOrderProposalResult
from schemas_manager_orders import ManagerOrderServiceLinePayload, ManagerOrderUpdatePayload
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_service import OrderService
from services.order_update.command import OrderUpdateCommandService
from services.order_proposal_version import proposal_version
from services.service_estimate_money import money
from services.tenant_entity_access_service import TenantEntityAccessService


async def _read_order(session, ctx, order_id):
    order = await TenantEntityAccessService.get_order(
        session,
        order_id,
        tenant_scope=ctx.tenant_scope,
        options=(
            selectinload(Order.proposals),
            selectinload(Order.service_links).selectinload(OrderServiceLink.service),
            selectinload(Order.product_links).selectinload(OrderProductLink.product),
        ),
        for_update=True,
        populate_existing=True,
    )
    if not order:
        raise HTTPException(404, "Order not found")
    return order


def _proposal(order, proposal_id):
    proposal = next((p for p in order.proposals if p.id == proposal_id and not p.is_archived), None)
    if not proposal:
        raise HTTPException(404, "Proposal not found")
    return proposal


async def _result(session, order, proposal):
    lines = sorted(
        (line for line in order.service_links if line.proposal_id == proposal.id), key=lambda x: x.id
    )
    products = sorted(
        (line for line in order.product_links if line.proposal_id == proposal.id), key=lambda x: x.id
    )
    total = sum(
        (money(item.price or 0) * (item.quantity or 0) for item in [*products, *lines]), Decimal("0.00")
    )
    return ServiceOrderProposalResult(
        order_id=order.id,
        proposal_id=proposal.id,
        proposal_status=proposal.status,
        version=await proposal_version(session, order.id, proposal.id),
        lines=[
            dict(
                id=line.id,
                service_id=line.service_id,
                title=line.title or (line.service.title if line.service else "Услуга"),
                description=line.description,
                unit=line.unit or "шт.",
                quantity=line.quantity,
                price=line.price,
                line_total=Decimal(str(line.price)) * line.quantity,
            )
            for line in lines
        ],
        products=[
            dict(
                id=line.id,
                product_id=line.product_id,
                title=line.title_snapshot or (line.product.title if line.product else "Товар"),
                quantity=line.quantity,
                price=line.price,
                line_total=Decimal(str(line.price)) * line.quantity,
            )
            for line in products
        ],
        total=total,
        currency="BYN",
        manager_url=f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/kanban?orderId={order.id}&proposalId={proposal.id}",
    )


async def get_service_order_proposal(session, ctx, data):
    order = await _read_order(session, ctx, data.order_id)
    return await _result(session, order, _proposal(order, data.proposal_id))


async def edit_service_order_proposal(session, ctx, data):
    if (
        data.action == "add"
        and (data.line is None or data.line_id is not None)
        or data.action == "update"
        and (data.line is None or data.line_id is None)
        or data.action == "delete"
        and (data.line is not None or data.line_id is None)
    ):
        raise HTTPException(422, "Supply a line for add/update and a line_id for update/delete")
    try:
        order = await OrderProposalCommandService._load_order_for_write(
            session, data.order_id, tenant_scope=ctx.tenant_scope
        )
    except ValueError as exc:
        raise HTTPException(404, str(exc)) from exc
    proposal = _proposal(order, data.proposal_id)
    if order.workflow_type not in {"repair", "service_work"}:
        raise HTTPException(409, "Only service and repair orders are supported")
    if OrderService._status_value(order.status) != "negotiation":
        raise HTTPException(409, "Service editing requires an order in negotiation")
    if await proposal_version(session, order.id, proposal.id) != data.expected_version:
        raise HTTPException(409, "Proposal changed; reload before editing")
    current = [item for item in order.service_links if item.proposal_id == proposal.id]
    target = next((item for item in current if item.id == data.line_id), None)
    if data.action != "add" and target is None:
        raise HTTPException(404, "Service line not found in proposal")
    if target is not None and (
        target.service_id is not None or target.installation_estimate_revision_id is not None
    ):
        raise HTTPException(409, "Only free service lines can be edited here")
    payload_lines = []
    for item in current:
        if item is target and data.action == "delete":
            continue
        values = dict(
            link_id=item.id,
            proposal_id=proposal.id,
            service_id=item.service_id,
            title=item.title or (item.service.title if item.service else "Услуга"),
            quantity=item.quantity,
            price=item.price,
            cost=item.cost,
        )
        if item is target and data.action == "update":
            values.update(data.line.model_dump())
        payload_lines.append(ManagerOrderServiceLinePayload(**values))
    if data.action == "add":
        payload_lines.append(ManagerOrderServiceLinePayload(proposal_id=proposal.id, **data.line.model_dump()))
    payload = ManagerOrderUpdatePayload(line_proposal_id=proposal.id, services=payload_lines)
    try:
        await OrderUpdateCommandService.update_order_for_manager(
            session, order.id, payload, tenant_scope=ctx.tenant_scope
        )
    except ValueError as exc:
        raise HTTPException(409, str(exc)) from exc
    order = await _read_order(session, ctx, order.id)
    return await _result(session, order, _proposal(order, data.proposal_id))
