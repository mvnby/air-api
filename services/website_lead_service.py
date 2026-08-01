"""Service-layer orchestration for website lead capture flows."""

from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from crud.product import ProductDAO
from models import LeadSource, Order, OrderStatus, Product
from schemas import (
    LeadCreatePayload,
    ProductAvailabilityLeadPayload,
    ProductAvailabilityLeadResponse,
    PublicContactLeadPayload,
    PublicContactLeadResponse,
)
from services.communications.tenant_website_event_service import (
    TenantWebsiteEventService,
)
from services.lead_service import LeadService
from services.order_service import OrderService
from services.public_write_fingerprint_service import PublicWriteFingerprintService
from services.public_write_idempotency_service import (
    PublicWriteCommandResponse,
    PublicWriteIdempotencyService,
)
from services.tenant_scope_service import (
    TenantScope,
    storefront_scope_clause,
)


class WebsiteLeadService:
    PRODUCT_AVAILABILITY_LOOKBACK_DAYS = 14
    PRODUCT_AVAILABILITY_NOTIFY_COOLDOWN_HOURS = 24

    @staticmethod
    async def create_contact_lead(
        session: AsyncSession,
        payload: PublicContactLeadPayload,
        *,
        tenant_scope: TenantScope,
        idempotency_key: str,
    ) -> PublicContactLeadResponse:
        request_key_hash = PublicWriteIdempotencyService.key_hash(
            idempotency_key
        )

        async def create() -> PublicWriteCommandResponse[PublicContactLeadResponse]:
            response = await WebsiteLeadService._create_contact_lead_mutation(
                session,
                payload,
                tenant_scope=tenant_scope,
                request_key_hash=request_key_hash,
            )
            return PublicWriteCommandResponse(
                value=response,
                resource_type="lead",
                resource_id=response.lead_id,
            )

        outcome = await PublicWriteIdempotencyService.execute(
            session,
            tenant_scope=tenant_scope,
            command_name="public_contact_lead_v1",
            idempotency_key=idempotency_key,
            request_fingerprint=PublicWriteFingerprintService.for_payload(payload),
            response_model=PublicContactLeadResponse,
            operation=create,
        )
        return outcome.value

    @staticmethod
    async def _create_contact_lead_mutation(
        session: AsyncSession,
        payload: PublicContactLeadPayload,
        *,
        tenant_scope: TenantScope,
        request_key_hash: str,
    ) -> PublicContactLeadResponse:
        request_lines = ["Заявка с сайта"]
        if payload.address:
            request_lines.append(f"Адрес/район: {payload.address}")
        if payload.message:
            request_lines.append(payload.message)

        lead_data = await LeadService.create_lead(
            session,
            LeadCreatePayload(
                source="site",
                name=payload.name,
                phone=payload.phone,
                email=payload.email,
                request_text="\n".join(request_lines),
            ),
            tenant_scope=tenant_scope,
        )
        response = PublicContactLeadResponse(
            lead_id=int(lead_data["id"]),
            status=str(lead_data["status"]),
            created_at=lead_data["created_at"],
        )
        await TenantWebsiteEventService.enqueue_contact_lead(
            session,
            lead_id=response.lead_id,
            status=response.status,
            name=payload.name,
            phone=payload.phone,
            email=payload.email,
            address=payload.address,
            message=payload.message,
            tenant_scope=tenant_scope,
            request_key_hash=request_key_hash,
        )
        return response

    @staticmethod
    async def create_product_availability_lead(
        session: AsyncSession,
        payload: ProductAvailabilityLeadPayload,
        *,
        tenant_scope: TenantScope,
        idempotency_key: str,
    ) -> ProductAvailabilityLeadResponse:
        request_key_hash = PublicWriteIdempotencyService.key_hash(
            idempotency_key
        )

        async def create() -> PublicWriteCommandResponse[ProductAvailabilityLeadResponse]:
            response = await WebsiteLeadService._create_product_availability_mutation(
                session,
                payload,
                tenant_scope=tenant_scope,
                request_key_hash=request_key_hash,
            )
            return PublicWriteCommandResponse(
                value=response,
                resource_type="order",
                resource_id=response.lead_id,
            )

        outcome = await PublicWriteIdempotencyService.execute(
            session,
            tenant_scope=tenant_scope,
            command_name="public_product_availability_lead_v1",
            idempotency_key=idempotency_key,
            request_fingerprint=PublicWriteFingerprintService.for_payload(payload),
            response_model=ProductAvailabilityLeadResponse,
            operation=create,
        )
        return outcome.value

    @staticmethod
    async def _create_product_availability_mutation(
        session: AsyncSession,
        payload: ProductAvailabilityLeadPayload,
        *,
        tenant_scope: TenantScope,
        request_key_hash: str,
    ) -> ProductAvailabilityLeadResponse:
        product = await ProductDAO.get_by_id(session, payload.product_id)
        if not product or not product.is_published:
            raise LookupError(f"Product with id={payload.product_id} not found")

        now = datetime.now()
        existing_order = await WebsiteLeadService._find_recent_product_availability_order(
            session=session,
            tenant_scope=tenant_scope,
            product_id=product.id,
            phone=payload.phone,
            now=now,
        )

        if existing_order:
            should_enqueue = WebsiteLeadService._should_enqueue_notification(
                existing_order,
                now,
            )
            order = await WebsiteLeadService._reuse_existing_order(
                session=session,
                order=existing_order,
                product=product,
                payload=payload,
                now=now,
            )
            if should_enqueue:
                await TenantWebsiteEventService.enqueue_availability(
                    session,
                    order=order,
                    product=product,
                    name=payload.name,
                    phone=payload.phone,
                    is_repeat=True,
                    tenant_scope=tenant_scope,
                    request_key_hash=request_key_hash,
                )
                WebsiteLeadService._set_order_meta(
                    order,
                    product_id=int(product.id or 0),
                    requested_at=now,
                    notified_at=now,
                )
                order.updated_at = now
                session.add(order)
            return ProductAvailabilityLeadResponse(
                lead_id=int(order.id or 0),
                status=str(
                    order.status.value
                    if hasattr(order.status, "value")
                    else order.status
                ),
                created_at=order.created_at,
            )

        order = await OrderService.create_from_website(
            session=session,
            customer_name=(payload.name or "").strip() or "Запрос на поступление",
            customer_phone=payload.phone,
            customer_email=None,
            customer_address=None,
            items=[],
            lead_source=LeadSource.SITE,
            initial_status=OrderStatus.NEW_LEAD,
            comment=WebsiteLeadService._build_request_text(product),
            tenant_scope=tenant_scope,
            commit=False,
        )
        WebsiteLeadService._set_order_meta(
            order,
            product_id=product.id,
            requested_at=now,
            notified_at=None,
        )
        session.add(order)
        await TenantWebsiteEventService.enqueue_availability(
            session,
            order=order,
            product=product,
            name=payload.name,
            phone=payload.phone,
            is_repeat=False,
            tenant_scope=tenant_scope,
            request_key_hash=request_key_hash,
        )
        WebsiteLeadService._set_order_meta(
            order,
            product_id=int(product.id or 0),
            requested_at=now,
            notified_at=now,
        )
        order.updated_at = now
        session.add(order)
        return ProductAvailabilityLeadResponse(
            lead_id=int(order.id or 0),
            status=str(
                order.status.value
                if hasattr(order.status, "value")
                else order.status
            ),
            created_at=order.created_at,
        )

    @staticmethod
    def _build_request_text(product: Product) -> str:
        return f"Сообщить о поступлении: {product.title} (slug: {product.slug}, product_id: {product.id})"

    @staticmethod
    async def _find_recent_product_availability_order(
        session: AsyncSession,
        tenant_scope: TenantScope,
        product_id: int,
        phone: str,
        now: datetime,
    ) -> Order | None:
        cutoff = now - timedelta(days=WebsiteLeadService.PRODUCT_AVAILABILITY_LOOKBACK_DAYS)
        stmt = (
            select(Order)
            .options(selectinload(Order.customer))
            .where(
                Order.lead_source == LeadSource.SITE,
                Order.created_at >= cutoff,
                storefront_scope_clause(Order, tenant_scope),
            )
            .order_by(Order.created_at.desc())
        )
        result = await session.execute(stmt)
        orders = list(result.scalars().all())
        normalized_phone = LeadService._normalize_phone_digits(phone)
        for order in orders:
            meta = order.technical_meta or {}
            if meta.get("availability_product_id") != product_id:
                continue
            customer_phone = order.customer.phone if order.customer else None
            if LeadService._normalize_phone_digits(customer_phone) == normalized_phone:
                return order
        return None

    @staticmethod
    def _should_enqueue_notification(order: Order, now: datetime) -> bool:
        technical_meta = order.technical_meta or {}
        last_notified_raw = technical_meta.get("availability_last_notified_at")
        if not last_notified_raw:
            return True
        try:
            last_notified_at = datetime.fromisoformat(str(last_notified_raw))
        except ValueError:
            return True
        cooldown = now - timedelta(hours=WebsiteLeadService.PRODUCT_AVAILABILITY_NOTIFY_COOLDOWN_HOURS)
        return last_notified_at <= cooldown

    @staticmethod
    async def _reuse_existing_order(
        session: AsyncSession,
        order: Order,
        product: Product,
        payload: ProductAvailabilityLeadPayload,
        now: datetime,
    ) -> Order:
        if order.customer:
            cleaned_name = (payload.name or "").strip()
            if cleaned_name:
                order.customer.name = cleaned_name
                session.add(order.customer)

        order.comment = WebsiteLeadService._build_request_text(product)
        order.status = OrderStatus.NEW_LEAD
        order.closing_result = None
        order.closed_at = None
        WebsiteLeadService._set_order_meta(
            order,
            product_id=product.id,
            requested_at=now,
            notified_at=None,
        )
        session.add(order)
        return order

    @staticmethod
    def _set_order_meta(
        order: Order,
        *,
        product_id: int,
        requested_at: datetime,
        notified_at: datetime | None,
    ) -> None:
        new_meta = dict(order.technical_meta or {})
        new_meta["availability_product_id"] = product_id
        new_meta["availability_last_requested_at"] = requested_at.isoformat()
        if notified_at is not None:
            new_meta["availability_last_notified_at"] = notified_at.isoformat()
        order.technical_meta = new_meta
        flag_modified(order, "technical_meta")
