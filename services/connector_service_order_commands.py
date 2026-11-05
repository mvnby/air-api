"""Bind the service-order tools to actor-scoped durable receipts and live reads."""

from pydantic import BaseModel

from schemas_connector_service_order_create import ConnectorServiceOrderResult
from schemas_connector_service_order_document import ServiceOrderContractReadInput
from services.authenticated_command_service import AuthenticatedCommandService
from services.connector_query_service import ConnectorQueryService
from services.connector_service_order_create import create_service_order, validate_service_order_create_access
from services.connector_service_order_document import get_service_order_contract, prepare_service_order_contract
from services.connector_service_order_lines import edit_service_order_proposal, get_service_order_proposal
from services.public_write_idempotency_service import PublicWriteCommandResponse
from services.tenant_entity_access_service import TenantEntityAccessService


class _SavedResource(BaseModel):
    id: int


async def execute_service_order_tool(session, actor, name, inputs):
    if name == "get_service_order_intake":
        return await ConnectorQueryService.service_order_intake(session, actor, inputs.order_id)
    if name == "get_service_order_proposal":
        return await get_service_order_proposal(session, actor, inputs)
    if name == "get_service_order_contract":
        return await get_service_order_contract(session, actor, inputs)

    if name == "create_service_order":
        # Manager requires its staff/membership fence before any child FK insert,
        # including the idempotency receipt.
        await validate_service_order_create_access(session, actor, inputs)

    result = None

    async def operation():
        nonlocal result
        if name == "create_service_order":
            result = await create_service_order(session, actor, inputs)
            return PublicWriteCommandResponse(result, resource_type="order", resource_id=result.order_id)
        if name == "edit_service_order_proposal":
            result = await edit_service_order_proposal(session, actor, inputs)
            resource_type, resource_id = "order_proposal", result.proposal_id
        elif name == "prepare_service_order_contract":
            result = await prepare_service_order_contract(session, actor, inputs)
            resource_type, resource_id = "order_document", result.document_id
        else:
            raise ValueError("Unknown service-order command")
        # A proposal can contain lengthy descriptions. Store its identity rather
        # than an unbounded copy or an obsolete claim that a draft is current.
        return PublicWriteCommandResponse(
            _SavedResource(id=resource_id), resource_type=resource_type, resource_id=resource_id
        )

    outcome = await AuthenticatedCommandService.execute(
        session,
        actor=actor,
        command_name=name,
        idempotency_key=inputs.idempotency_key,
        payload=inputs.model_dump(mode="json", exclude={"idempotency_key"}),
        response_model=ConnectorServiceOrderResult if name == "create_service_order" else _SavedResource,
        operation=operation,
    )
    if outcome.replayed:
        if name == "create_service_order":
            result = outcome.value
            if (
                await TenantEntityAccessService.get_order(
                    session, result.order_id, tenant_scope=actor.tenant_scope
                )
                is None
            ):
                raise LookupError("Order not found")
        elif name == "edit_service_order_proposal":
            result = await get_service_order_proposal(session, actor, inputs)
        else:
            result = await get_service_order_contract(
                session, actor, ServiceOrderContractReadInput(document_id=outcome.value.id)
            )
    return {"result": result, "replayed": outcome.replayed}
