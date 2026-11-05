"""Compose existing Manager commands into a draft-only service order.

The MCP dispatcher authenticates the actor, requires the service-order scope,
and wraps this command in its durable idempotency receipt and audit boundary.
"""

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.command_actor import CommandActor
from core.config import settings
from models import CustomerBranch, OrderStatus
from schemas_connector_service_order_create import (
    ConnectorServiceOrderResult,
    ServiceOrderCreateInput,
)
from schemas_manager_leads import LeadQualifyPayload
from schemas_manager_orders import ManagerOrderCreatePayload, ManagerOrderUpdatePayload
from services.command_transaction import command_transaction
from services.lead_command_service import LeadCommandService
from services.lead_service import LeadVersionConflict
from services.order_create_command_service import OrderCreateCommandService
from services.order_proposal_command_service import OrderProposalCommandService
from services.order_responsibility_service import OrderResponsibilityService
from services.order_scenarios import resolve_scenario
from services.order_service import OrderService
from services.order_update.command import OrderUpdateCommandService
from services.tenant_entity_access_service import TenantEntityAccessService as Access


async def validate_service_order_create_access(session, ctx, data):
    """Revalidate resource access before both receipt claim and receipt replay."""
    scope = ctx.tenant_scope
    responsible = await OrderResponsibilityService.initial_responsible(session, scope, ctx.staff_user_id)
    if responsible is None:
        raise HTTPException(403, "Active company staff membership required")
    customer = await Access.get_customer(session, data.customer_id, tenant_scope=scope)
    if customer is None or customer.is_archived:
        raise HTTPException(404, "Active customer not found")
    if data.customer_branch_id is not None:
        branch = await session.get(CustomerBranch, data.customer_branch_id)
        if branch is None or branch.customer_id != data.customer_id:
            raise HTTPException(404, "Customer branch not found")
    if data.incoming_id is not None:
        if await Access.get_lead(session, data.incoming_id, tenant_scope=scope) is None:
            raise HTTPException(404, "Incoming request not found")
    if data.incoming_order_id is not None:
        if await Access.get_order(session, data.incoming_order_id, tenant_scope=scope) is None:
            raise HTTPException(404, "Incoming order not found")


async def create_service_order(
    session: AsyncSession,
    ctx: CommandActor,
    data: ServiceOrderCreateInput,
) -> ConnectorServiceOrderResult:
    scope = ctx.tenant_scope
    async with command_transaction(session):
        await validate_service_order_create_access(session, ctx, data)
        workflow, service = resolve_scenario(workflow_type=data.workflow_type, service_type=data.service_type)
        incoming_version = None
        if data.incoming_order_id is not None:
            incoming = await Access.get_order(
                session,
                data.incoming_order_id,
                tenant_scope=scope,
                for_update=True,
                populate_existing=True,
            )
            if incoming is None:
                raise HTTPException(404, "Incoming order not found")
            if incoming.workflow_revision != data.expected_incoming_order_revision:
                raise HTTPException(409, "Incoming order has changed; reload its current revision")
            if incoming.status != OrderStatus.NEW_LEAD or incoming.linked_order_id is not None:
                raise HTTPException(409, "Only an unlinked incoming order can be qualified")
            if incoming.customer_id is not None and incoming.customer_id != data.customer_id:
                raise HTTPException(409, "Incoming order already belongs to another customer")
            if (
                data.customer_branch_id is not None
                and incoming.customer_branch_id is not None
                and data.customer_branch_id != incoming.customer_branch_id
            ):
                raise HTTPException(409, "Incoming order already belongs to another customer branch")
            changes = dict(
                status="negotiation",
                customer_id=data.customer_id,
                workflow_type=workflow,
                service_type=service,
            )
            if data.customer_branch_id is not None:
                changes["customer_branch_id"] = data.customer_branch_id
            if data.address is not None:
                changes["customer_delivery_address"] = data.address
            if data.title is not None:
                changes["title"] = data.title
            if data.request_text and data.request_text.strip() != (incoming.comment or "").strip():
                changes["comment"] = (
                    f"{incoming.comment}\n\n{data.request_text}" if incoming.comment else data.request_text
                )
            # Manager links the verified customer before qualification. Omit
            # customer requisites, commercial arrays, dates and assignments.
            created = await OrderUpdateCommandService.update_order_for_manager(
                session,
                int(incoming.id),
                ManagerOrderUpdatePayload(**changes),
                tenant_scope=scope,
            )
            order_id = int(created["id"])
        elif data.incoming_id is None:
            created = await OrderCreateCommandService.create_manager_order(
                session,
                ManagerOrderCreatePayload(
                    customer_id=data.customer_id,
                    source="manager",
                    workflow_type=workflow,
                    service_type=service,
                    request_text=data.request_text or "",
                    title=data.title,
                    customer_branch_id=data.customer_branch_id,
                    address=data.address,
                ),
                tenant_scope=scope,
                creator_staff_user_id=ctx.staff_user_id,
            )
            order_id = int(created["id"])
        else:
            lead = await Access.get_lead(
                session,
                data.incoming_id,
                tenant_scope=scope,
                for_update=True,
                populate_existing=True,
            )
            if lead is None:
                raise HTTPException(404, "Incoming request not found")
            if lead.version != data.expected_incoming_version:
                raise LeadVersionConflict("Incoming request has changed; reload its current version")
            if lead.converted_order_id is not None:
                raise HTTPException(
                    409,
                    f"Incoming request already linked to order {lead.converted_order_id}",
                )
            # Preserve the source verbatim on Lead and in the order comment. An
            # explicit additional instruction may supplement that source.
            comment = lead.request_text or ""
            if data.request_text and data.request_text.strip() != comment.strip():
                comment = f"{comment}\n\n{data.request_text}" if comment else data.request_text
            created = await LeadCommandService.qualify_lead(
                session,
                data.incoming_id,
                LeadQualifyPayload(
                    customer_id=data.customer_id,
                    customer_branch_id=data.customer_branch_id,
                    expected_version=data.expected_incoming_version,
                    workflow_type=workflow,
                    service_type=service,
                    order_comment=comment,
                    delivery_address=data.address,
                ),
                tenant_scope=scope,
                creator_staff_user_id=ctx.staff_user_id,
            )
            order_id = int(created["order_id"])
            incoming_version = int(lead.version)
        order = await OrderProposalCommandService._load_order_for_write(session, order_id, tenant_scope=scope)
        if order.status != OrderStatus.NEGOTIATION:
            raise HTTPException(409, "Service order must be in negotiations")
        if data.title is not None:
            order.title = OrderService._clean_order_title(data.title)
            session.add(order)
        proposal = OrderService._selected_proposal(order)
        if proposal is None or proposal.is_archived or proposal.status != "draft":
            raise HTTPException(409, "Editable proposal is required")
        await session.flush()
        url = f"{settings.MANAGER_BASE_URL.rstrip('/')}/orders/kanban?orderId={order_id}"
        return ConnectorServiceOrderResult(
            order_id=order_id,
            customer_id=data.customer_id,
            proposal_id=int(proposal.id),
            status=OrderService._status_value(order.status),
            proposal_status=proposal.status,
            workflow_type=workflow,
            service_type=service,
            incoming_id=data.incoming_id,
            incoming_version=incoming_version,
            incoming_order_id=data.incoming_order_id,
            incoming_order_revision=int(order.workflow_revision) if data.incoming_order_id is not None else None,
            manager_url=url,
            proposal_manager_url=f"{url}&proposalId={proposal.id}",
        )
