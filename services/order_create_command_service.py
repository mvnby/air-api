"""Transactional Manager order creation command."""

from typing import Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from models import LeadSource, OrderStatus
from services.command_transaction import command_transaction
from services.order_projection_service import OrderProjectionService
from services.order_service import OrderService
from services.tenant_scope_service import TenantScope


class OrderCreateCommandService:
    @staticmethod
    async def create_manager_order(
        session: AsyncSession,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        async with command_transaction(session):
            source = (
                LeadSource(payload.source)
                if payload.source
                else LeadSource.MANAGER
            )
            initial_status = (
                OrderStatus.NEGOTIATION
                if payload.customer_id or payload.service_type == "maintenance"
                else OrderStatus.NEW_LEAD
            )

            order = await OrderService.create_from_website(
                session=session,
                customer_name=payload.name or "Новый клиент",
                customer_phone=payload.phone or "",
                customer_email=None,
                customer_address=payload.address,
                items=[],
                lead_source=source,
                initial_status=initial_status,
                comment=payload.request_text,
                customer_id=payload.customer_id,
                customer_type=payload.customer_type,
                customer_inn=payload.customer_inn,
                customer_full_legal_name=payload.customer_full_legal_name,
                tenant_scope=tenant_scope,
                commit=False,
            )

            default_title = OrderService._build_default_order_title(
                service_type=payload.service_type,
                comment=payload.request_text,
            )
            if default_title:
                order.title = default_title

            if payload.service_type == "maintenance" and payload.target_date:
                order.installation_date = OrderService._normalize_naive_datetime(
                    payload.target_date
                )

            if payload.service_type:
                order.technical_meta = dict(order.technical_meta or {})
                order.technical_meta["service_type"] = payload.service_type
                order.workflow_type = OrderService._workflow_type_from_service_type(
                    payload.service_type,
                    order.workflow_type,
                )
                flag_modified(order, "technical_meta")

            if order.workflow_type == "repair":
                OrderService._ensure_repair_meta_defaults(order)
                flag_modified(order, "technical_meta")
                await OrderService._maybe_add_default_repair_diagnostic(
                    session,
                    order,
                )

            session.add(order)
            await session.flush()
            order_id = int(order.id)

        data = await OrderProjectionService.get_order_detail_for_manager(
            session,
            order_id,
            tenant_scope=tenant_scope,
        )
        if data is None:
            raise RuntimeError("Committed order is no longer visible in its tenant scope")
        return data
