"""Transactional Manager order creation command."""

from typing import Any, Dict
from hashlib import sha256

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from models import CustomerBranch, LeadSource, Order, OrderStatus
from services.command_transaction import command_transaction
from services.order_projection_service import OrderProjectionService
from services.order_service import OrderService
from services.order_scenarios import WORKFLOW_LABELS, resolve_scenario
from services.tenant_scope_service import TenantScope, storefront_scope_clause


class OrderCreateCommandService:
    @staticmethod
    async def create_manager_order(
        session: AsyncSession,
        payload: Any,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any]:
        request_id = getattr(payload, "client_request_id", None)
        fingerprint = (
            sha256(f"manager-order:{request_id}".encode()).hexdigest()
            if request_id is not None else None
        )
        if fingerprint is not None:
            existing = await OrderCreateCommandService._find_existing_order(
                session, fingerprint, tenant_scope=tenant_scope
            )
            if existing is not None:
                return existing
        try:
            return await OrderCreateCommandService._create_manager_order_once(
                session, payload, tenant_scope=tenant_scope,
                fingerprint=fingerprint,
            )
        except IntegrityError:
            if fingerprint is None:
                raise
            await session.rollback()
            existing = await OrderCreateCommandService._find_existing_order(
                session, fingerprint, tenant_scope=tenant_scope
            )
            if existing is None:
                raise
            return existing

    @staticmethod
    async def _find_existing_order(
        session: AsyncSession,
        fingerprint: str,
        *,
        tenant_scope: TenantScope,
    ) -> Dict[str, Any] | None:
        order_id = (
            await session.execute(
                select(Order.id).where(
                    Order.source_fingerprint == fingerprint,
                    storefront_scope_clause(Order, tenant_scope),
                )
            )
        ).scalar_one_or_none()
        if order_id is None:
            return None
        return await OrderProjectionService.get_order_detail_for_manager(
            session, int(order_id), tenant_scope=tenant_scope,
        )

    @staticmethod
    async def _create_manager_order_once(
        session: AsyncSession,
        payload: Any,
        *,
        tenant_scope: TenantScope,
        fingerprint: str | None,
    ) -> Dict[str, Any]:
        async with command_transaction(session):
            explicit_workflow = payload.workflow_type is not None
            workflow_type, service_type = resolve_scenario(
                workflow_type=payload.workflow_type,
                service_type=payload.service_type,
            )
            if not workflow_type and not str(payload.request_text or "").strip():
                raise ValueError("request_text or scenario is required")
            source = (
                LeadSource(payload.source)
                if payload.source
                else LeadSource.MANAGER
            )
            initial_status = (
                OrderStatus.NEGOTIATION
                if payload.customer_id or explicit_workflow or service_type == "maintenance"
                else OrderStatus.NEW_LEAD
            )

            order = await OrderService.create_from_website(
                session=session,
                customer_name=payload.name or "Новый клиент",
                customer_phone=payload.phone or "",
                customer_email=None,
                # Worksite address belongs to the order, not the customer's requisites.
                customer_address=None,
                items=[],
                lead_source=source,
                initial_status=initial_status,
                comment=payload.request_text or None,
                customer_id=payload.customer_id,
                customer_type=None if payload.customer_id else payload.customer_type,
                customer_inn=None if payload.customer_id else payload.customer_inn,
                customer_full_legal_name=(
                    None if payload.customer_id else payload.customer_full_legal_name
                ),
                tenant_scope=tenant_scope,
                commit=False,
            )
            if fingerprint is not None:
                order.source_fingerprint = fingerprint

            branch = None
            if payload.customer_branch_id is not None:
                branch = (
                    await session.execute(
                        select(CustomerBranch).where(
                            CustomerBranch.id == payload.customer_branch_id,
                            CustomerBranch.customer_id == order.customer_id,
                        )
                    )
                ).scalars().first()
                if branch is None:
                    raise ValueError("Selected customer branch not found")
                order.customer_branch_id = int(branch.id)

            order.delivery_address = payload.address or (
                branch.delivery_address if branch else None
            )
            default_title = (
                OrderService._clean_order_title(payload.title)
                if payload.title is not None
                else (
                    WORKFLOW_LABELS[workflow_type]
                    if workflow_type and service_type is None
                    else OrderService._build_default_order_title(
                        service_type=service_type,
                        comment=payload.request_text,
                    )
                )
            )
            if default_title:
                order.title = default_title

            if not explicit_workflow and service_type == "maintenance" and payload.target_date:
                order.installation_date = OrderService._normalize_naive_datetime(
                    payload.target_date
                )

            if workflow_type or payload.target_date or payload.contact_name or payload.contact_phone:
                order.technical_meta = dict(order.technical_meta or {})
                if workflow_type:
                    order.workflow_type = workflow_type
                    if service_type is not None:
                        order.technical_meta["service_type"] = service_type
                    else:
                        order.technical_meta.pop("service_type", None)
                if explicit_workflow and payload.target_date:
                    order.technical_meta["requested_date"] = payload.target_date.date().isoformat()
                if payload.contact_name:
                    order.technical_meta["contact_name"] = payload.contact_name.strip()
                if payload.contact_phone:
                    order.technical_meta["contact_phone"] = payload.contact_phone.strip()
                flag_modified(order, "technical_meta")

            if order.workflow_type == "repair":
                OrderService._ensure_repair_meta_defaults(order)
                flag_modified(order, "technical_meta")
                if not explicit_workflow:
                    await OrderService._maybe_add_default_repair_diagnostic(
                        session,
                        order,
                        tenant_scope=tenant_scope,
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
