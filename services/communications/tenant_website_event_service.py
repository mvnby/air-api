"""Transactional producers for tenant-scoped website communications."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Customer, Lead, Order, OrderProductLink, OrderServiceLink, Product
from schemas import OrderPayload
from services.communications.contracts import (
    PublicOrderCustomerSnapshotV1,
    PublicOrderProductLineSnapshotV1,
    PublicOrderServiceLineSnapshotV1,
    TenantWebsiteAvailabilityRequestedPayloadV1,
    TenantWebsiteCheckoutCreatedPayloadV1,
    TenantWebsiteContactLeadCreatedPayloadV1,
    TenantWebsiteRepairDiagnosticCreatedPayloadV1,
)
from services.communications.outbox_service import IntegrationOutboxService
from services.communications.tenant_website_events import (
    TENANT_WEBSITE_AVAILABILITY_REQUESTED_EVENT,
    TENANT_WEBSITE_CHECKOUT_CREATED_EVENT,
    TENANT_WEBSITE_CONTACT_LEAD_CREATED_EVENT,
    TENANT_WEBSITE_REPAIR_DIAGNOSTIC_CREATED_EVENT,
)
from services.repair_diagnostic_contracts import RepairDiagnosticLeadPayload
from services.tenant_scope_service import TenantScope


class TenantWebsiteEventService:
    PRIORITY = 20
    MAX_ATTEMPTS = 8

    @staticmethod
    def _assert_order_scope(order: Order, tenant_scope: TenantScope) -> int:
        order_id = int(order.id or 0)
        if (
            order_id <= 0
            or int(order.tenant_id or 0) != tenant_scope.tenant_id
            or int(order.storefront_id or 0) != tenant_scope.storefront_id
        ):
            raise ValueError("Tenant website event order scope is invalid")
        return order_id

    @staticmethod
    def _idempotency_key(kind: str, request_key_hash: str) -> str:
        digest = str(request_key_hash or "").strip().lower()
        if len(digest) != 64 or any(
            char not in "0123456789abcdef" for char in digest
        ):
            raise ValueError("Tenant website event request key hash is invalid")
        return f"tenant-website-{kind}-v1:{digest}"

    @classmethod
    async def enqueue_checkout(
        cls,
        session: AsyncSession,
        *,
        order: Order,
        request: OrderPayload,
        tenant_scope: TenantScope,
        request_key_hash: str,
    ) -> None:
        order_id = cls._assert_order_scope(order, tenant_scope)
        customer = await session.get(Customer, int(order.customer_id or 0))
        if customer is None or int(customer.tenant_id or 0) != tenant_scope.tenant_id:
            raise ValueError("Tenant website checkout customer scope is invalid")

        product_rows = (
            await session.execute(
                select(OrderProductLink, Product)
                .outerjoin(Product, Product.id == OrderProductLink.product_id)
                .where(OrderProductLink.order_id == order_id)
                .order_by(OrderProductLink.id.asc())
            )
        ).all()
        service_links = list(
            (
                await session.execute(
                    select(OrderServiceLink)
                    .where(OrderServiceLink.order_id == order_id)
                    .order_by(OrderServiceLink.id.asc())
                )
            ).scalars()
        )
        payload = TenantWebsiteCheckoutCreatedPayloadV1(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            order_id=order_id,
            status=(
                order.status.value
                if hasattr(order.status, "value")
                else str(order.status)
            ),
            customer=PublicOrderCustomerSnapshotV1(
                name=request.customer.name,
                phone=request.customer.phone,
                email=request.customer.email,
                address=request.customer.address,
                customer_type=request.customer.type,
            ),
            comment=request.comment,
            total_amount=order.total_amount,
            product_lines=[
                PublicOrderProductLineSnapshotV1(
                    product_id=link.product_id,
                    title=(
                        product.title
                        if product is not None
                        else f"Product #{link.product_id}"
                    ),
                    quantity=link.quantity,
                    unit_price=link.price,
                    installation_included=link.is_installation_included,
                    installation_price=link.installation_price,
                )
                for link, product in product_rows
            ],
            service_lines=[
                PublicOrderServiceLineSnapshotV1(
                    service_id=link.service_id,
                    title=link.title or "Услуга",
                    quantity=link.quantity,
                    unit_price=link.price,
                )
                for link in service_links
            ],
        )
        await IntegrationOutboxService.enqueue(
            session,
            event_type=TENANT_WEBSITE_CHECKOUT_CREATED_EVENT,
            aggregate_type="order",
            aggregate_id=order_id,
            payload=payload,
            idempotency_key=cls._idempotency_key(
                "checkout",
                request_key_hash,
            ),
            priority=cls.PRIORITY,
            max_attempts=cls.MAX_ATTEMPTS,
        )

    @classmethod
    async def enqueue_contact_lead(
        cls,
        session: AsyncSession,
        *,
        lead_id: int,
        status: str,
        name: str,
        phone: str,
        email: str | None,
        address: str | None,
        message: str | None,
        tenant_scope: TenantScope,
        request_key_hash: str,
    ) -> None:
        lead = await session.get(Lead, lead_id)
        if (
            lead is None
            or int(lead.tenant_id or 0) != tenant_scope.tenant_id
            or int(lead.storefront_id or 0) != tenant_scope.storefront_id
        ):
            raise ValueError("Tenant website contact lead scope is invalid")
        payload = TenantWebsiteContactLeadCreatedPayloadV1(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            lead_id=lead_id,
            status=status,
            name=name,
            phone=phone,
            email=email,
            address=address,
            message=message,
        )
        await IntegrationOutboxService.enqueue(
            session,
            event_type=TENANT_WEBSITE_CONTACT_LEAD_CREATED_EVENT,
            aggregate_type="lead",
            aggregate_id=lead_id,
            payload=payload,
            idempotency_key=cls._idempotency_key("contact", request_key_hash),
            priority=cls.PRIORITY,
            max_attempts=cls.MAX_ATTEMPTS,
        )

    @classmethod
    async def enqueue_availability(
        cls,
        session: AsyncSession,
        *,
        order: Order,
        product: Product,
        name: str | None,
        phone: str,
        is_repeat: bool,
        tenant_scope: TenantScope,
        request_key_hash: str,
    ) -> None:
        order_id = cls._assert_order_scope(order, tenant_scope)
        payload = TenantWebsiteAvailabilityRequestedPayloadV1(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            order_id=order_id,
            status=(
                order.status.value
                if hasattr(order.status, "value")
                else str(order.status)
            ),
            product_id=int(product.id or 0),
            product_title=product.title,
            product_slug=product.slug,
            name=(name or "").strip() or None,
            phone=phone,
            is_repeat=is_repeat,
        )
        await IntegrationOutboxService.enqueue(
            session,
            event_type=TENANT_WEBSITE_AVAILABILITY_REQUESTED_EVENT,
            aggregate_type="order",
            aggregate_id=order_id,
            payload=payload,
            idempotency_key=cls._idempotency_key(
                "availability",
                request_key_hash,
            ),
            priority=cls.PRIORITY,
            max_attempts=cls.MAX_ATTEMPTS,
        )

    @classmethod
    async def enqueue_repair_diagnostic(
        cls,
        session: AsyncSession,
        *,
        order: Order,
        request: RepairDiagnosticLeadPayload,
        photo_count: int,
        symptom_label: str,
        tenant_scope: TenantScope,
        request_key_hash: str,
    ) -> None:
        order_id = cls._assert_order_scope(order, tenant_scope)
        payload = TenantWebsiteRepairDiagnosticCreatedPayloadV1(
            tenant_id=tenant_scope.tenant_id,
            storefront_id=tenant_scope.storefront_id,
            order_id=order_id,
            status=(
                order.status.value
                if hasattr(order.status, "value")
                else str(order.status)
            ),
            name=request.contact.name,
            phone=request.contact.phone,
            address=request.contact.address,
            symptom_label=symptom_label,
            photo_count=photo_count,
        )
        await IntegrationOutboxService.enqueue(
            session,
            event_type=TENANT_WEBSITE_REPAIR_DIAGNOSTIC_CREATED_EVENT,
            aggregate_type="order",
            aggregate_id=order_id,
            payload=payload,
            idempotency_key=cls._idempotency_key("repair", request_key_hash),
            priority=cls.PRIORITY,
            max_attempts=cls.MAX_ATTEMPTS,
        )
