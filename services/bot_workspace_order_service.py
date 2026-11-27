"""Source-bound service orders and customer-bound quick-order drafts."""

from api_contracts.bot_workspace import BotWorkspaceOrderResult
from schemas_connector_service_order_create import ServiceOrderCreateInput
from services.authenticated_command_service import AuthenticatedCommandService
from services.bot_quick_order_draft_service import BotQuickOrderDraftService
from services.bot_workspace_service import incoming_item
from services.connector_service_order_create import create_service_order, validate_service_order_create_access
from services.lead_service import LeadVersionConflict
from services.public_write_idempotency_service import PublicWriteCommandResponse
from services.tenant_entity_access_service import TenantEntityAccessService as Access


async def customer_draft(session, ws, customer_id, telegram_id):
    customer = await Access.get_customer(session, customer_id, tenant_scope=ws.scope, for_update=True)
    if customer is None or customer.is_archived:
        raise LookupError("Клиент не найден")
    return await BotQuickOrderDraftService.start(session, telegram_id=telegram_id, customer_id=customer_id, text="")


async def service_order_from_incoming(session, ws, item_id, payload):
    source = ({"incoming_id": item_id, "expected_incoming_version": payload.expected_version}
              if payload.kind == "lead" else
              {"incoming_order_id": item_id, "expected_incoming_order_revision": payload.expected_version})
    command = ServiceOrderCreateInput(customer_id=payload.customer_id, workflow_type=payload.workflow_type,
                                      idempotency_key=payload.idempotency_key, **source)
    await validate_service_order_create_access(session, ws.actor, command)

    async def qualify():
        lock = Access.get_lead if payload.kind == "lead" else Access.get_order
        if await lock(session, item_id, tenant_scope=ws.scope, for_update=True) is None:
            raise LookupError("Обращение не найдено")
        item = await incoming_item(session, ws, item_id, payload.kind)
        if item.archive or item.source_kind != "customer_request":
            raise LeadVersionConflict("Это обращение недоступно для перевода в сервисный заказ")
        # Preserve the source address and verbatim request. The Manager command
        # promotes an Order intake in place or links the qualified Lead to its order.
        result = await create_service_order(session, ws.actor, command.model_copy(update={
            "address": item.customer_delivery_address or None,
        }))
        return PublicWriteCommandResponse(value=BotWorkspaceOrderResult(order_id=result.order_id),
                                          resource_type="order", resource_id=result.order_id)

    outcome = await AuthenticatedCommandService.execute(
        session, actor=ws.actor, command_name=f"workspace.qualify.{payload.kind}.{item_id}",
        idempotency_key=payload.idempotency_key, payload=command.model_dump(exclude={"idempotency_key"}),
        response_model=BotWorkspaceOrderResult, operation=qualify,
    )
    if await Access.get_order(session, outcome.value.order_id, tenant_scope=ws.scope) is None:
        raise LookupError("Заказ не найден")
    return outcome.value
