"""Transactional command boundary for a full Manager order update."""

from typing import Any, Dict, Optional

from sqlalchemy.ext.asyncio import AsyncSession

from services.command_transaction import command_transaction
from services.order_projection_service import OrderProjectionService
from services.order_service import OrderService
from services.order_update.commercial_lines import apply_commercial_lines
from services.order_update.context import OrderUpdateContext
from services.order_update.customer_fields import apply_customer_fields
from services.order_update.finalize import finalize_order_update
from services.order_update.order_fields import apply_order_fields
from services.tenant_entity_access_service import TenantEntityAccessService
from services.tenant_scope_service import TenantScope


class OrderUpdateCommandService:
    @staticmethod
    async def update_order_for_manager(
        session: AsyncSession,
        order_id: int,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Optional[Dict[str, Any]]:
        async with command_transaction(session):
            order = await TenantEntityAccessService.get_order(
                session,
                order_id,
                tenant_scope=tenant_scope,
                for_update=True,
            )
            if not order:
                return None

            fields_set = getattr(payload, "model_fields_set", None)
            if fields_set is None:
                fields_set = getattr(payload, "__fields_set__", set())

            context = OrderUpdateContext(
                session=session,
                order_id=order_id,
                order=order,
                payload=payload,
                tenant_scope=tenant_scope,
                fields_set=set(fields_set),
                previous_workflow_type=OrderService._normalize_workflow_type(
                    getattr(order, "workflow_type", None)
                ),
                previous_status=order.status,
                previous_negotiation_status=OrderService._normalize_negotiation_status(
                    getattr(order, "negotiation_status", None)
                ),
                previous_execution_status=OrderService._normalize_execution_status(
                    getattr(order, "execution_status", None)
                ),
                previous_delivery_address=order.delivery_address,
            )

            await apply_order_fields(context)
            await apply_customer_fields(context)
            await apply_commercial_lines(context)
            await finalize_order_update(context)

        return await OrderProjectionService.get_order_detail_for_manager(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
