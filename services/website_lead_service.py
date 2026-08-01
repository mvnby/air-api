"""Service-layer orchestration for website lead capture flows."""

import logging
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
from services.bot_service import BotService
from services.lead_service import LeadService
from services.order_service import OrderService
from services.public_write_fingerprint_service import PublicWriteFingerprintService
from services.public_write_idempotency_service import (
    PublicWriteCommandResponse,
    PublicWriteIdempotencyService,
)
from services.staff_user_service import StaffUserService
from services.tenant_scope_service import (
    TenantScope,
    storefront_scope_clause,
)

logger = logging.getLogger(__name__)


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
        created_lead_id: int | None = None

        async def create() -> PublicWriteCommandResponse[PublicContactLeadResponse]:
            nonlocal created_lead_id
            response = await WebsiteLeadService._create_contact_lead_mutation(
                session,
                payload,
                tenant_scope=tenant_scope,
            )
            created_lead_id = response.lead_id
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
        if not outcome.replayed and created_lead_id is not None:
            await WebsiteLeadService._notify_contact_lead_admins(
                session=session,
                lead_id=created_lead_id,
                payload=payload,
                tenant_scope=tenant_scope,
            )
        return outcome.value

    @staticmethod
    async def _create_contact_lead_mutation(
        session: AsyncSession,
        payload: PublicContactLeadPayload,
        *,
        tenant_scope: TenantScope,
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
        return PublicContactLeadResponse(
            lead_id=int(lead_data["id"]),
            status=str(lead_data["status"]),
            created_at=lead_data["created_at"],
        )

    @staticmethod
    async def _notify_contact_lead_admins(
        *,
        session: AsyncSession,
        lead_id: int,
        payload: PublicContactLeadPayload,
        tenant_scope: TenantScope,
    ) -> None:
        admin_ids = await StaffUserService.get_active_owner_admin_telegram_recipient_ids(
            session,
            tenant_scope=tenant_scope,
        )
        if not admin_ids:
            return

        lines = [
            f"🔔 <b>ЗАЯВКА С САЙТА #{lead_id}</b>",
            f"👤 {BotService.escape_html(payload.name, max_length=160)}",
            f"📱 {BotService.escape_html(payload.phone, max_length=80)}",
        ]
        if payload.email:
            lines.append(f"📧 {BotService.escape_html(payload.email, max_length=254)}")
        if payload.address:
            lines.append(f"📍 {BotService.escape_html(payload.address, max_length=300)}")
        if payload.message:
            lines.extend(
                ["", f"💬 {BotService.escape_html(payload.message, max_length=800)}"]
            )
        text = "\n".join(lines)

        for admin_id in admin_ids:
            try:
                delivered = await BotService.send_message(admin_id, text)
                if not delivered:
                    logger.warning(
                        "WEBSITE_CONTACT_LEAD_DELIVERY_FAILED lead_id=%s admin_id=%s",
                        lead_id,
                        admin_id,
                    )
            except Exception:
                logger.exception(
                    "WEBSITE_CONTACT_LEAD_SEND_FAILED lead_id=%s admin_id=%s",
                    lead_id,
                    admin_id,
                )

    @staticmethod
    async def create_product_availability_lead(
        session: AsyncSession,
        payload: ProductAvailabilityLeadPayload,
        *,
        tenant_scope: TenantScope,
        idempotency_key: str,
    ) -> ProductAvailabilityLeadResponse:
        notification: tuple[Order, Product, bool] | None = None

        async def create() -> PublicWriteCommandResponse[ProductAvailabilityLeadResponse]:
            nonlocal notification
            response, notification = (
                await WebsiteLeadService._create_product_availability_mutation(
                    session,
                    payload,
                    tenant_scope=tenant_scope,
                )
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
        if not outcome.replayed and notification is not None:
            order, product, is_repeat = notification
            await WebsiteLeadService._notify_admins(
                session=session,
                order=order,
                product=product,
                payload=payload,
                now=datetime.now(),
                is_repeat=is_repeat,
                tenant_scope=tenant_scope,
            )
        return outcome.value

    @staticmethod
    async def _create_product_availability_mutation(
        session: AsyncSession,
        payload: ProductAvailabilityLeadPayload,
        *,
        tenant_scope: TenantScope,
    ) -> tuple[ProductAvailabilityLeadResponse, tuple[Order, Product, bool] | None]:
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
            should_notify = WebsiteLeadService._should_notify_admins(existing_order, now)
            order = await WebsiteLeadService._reuse_existing_order(
                session=session,
                order=existing_order,
                product=product,
                payload=payload,
                now=now,
            )
            return (
                ProductAvailabilityLeadResponse(
                    lead_id=int(order.id or 0),
                    status=str(order.status.value if hasattr(order.status, "value") else order.status),
                    created_at=order.created_at,
                ),
                (order, product, True) if should_notify else None,
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

        return (
            ProductAvailabilityLeadResponse(
                lead_id=int(order.id or 0),
                status=str(order.status.value if hasattr(order.status, "value") else order.status),
                created_at=order.created_at,
            ),
            (order, product, False),
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
    def _should_notify_admins(order: Order, now: datetime) -> bool:
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

    @staticmethod
    async def _notify_admins(
        session: AsyncSession,
        order: Order,
        product: Product,
        payload: ProductAvailabilityLeadPayload,
        now: datetime,
        is_repeat: bool,
        tenant_scope: TenantScope,
    ) -> None:
        admin_ids = await StaffUserService.get_active_owner_admin_telegram_recipient_ids(
            session,
            tenant_scope=tenant_scope,
        )
        if not admin_ids:
            return

        message_lines = [
            "🔔 <b>ПОВТОРНЫЙ ЗАПРОС НА ПОСТУПЛЕНИЕ</b>" if is_repeat else "🔔 <b>ЗАПРОС НА ПОСТУПЛЕНИЕ С САЙТА</b>",
            f"🆔 Заявка #{order.id}",
            f"📦 {BotService.escape_html(product.title, max_length=180)}",
            f"🔗 /product/{BotService.escape_html(product.slug, max_length=200)}",
            f"📱 {BotService.escape_html(payload.phone, max_length=80)}",
        ]
        if payload.name and payload.name.strip():
            message_lines.insert(
                4,
                f"👤 {BotService.escape_html(payload.name.strip(), max_length=160)}",
            )

        admin_text = "\n".join(message_lines)
        for admin_id in admin_ids:
            try:
                delivered = await BotService.send_message(admin_id, admin_text)
                if not delivered:
                    logger.warning(
                        "WEBSITE_AVAILABILITY_NOTIFY_DELIVERY_FAILED order_id=%s admin_id=%s",
                        order.id,
                        admin_id,
                    )
            except Exception:
                logger.exception(
                    "WEBSITE_AVAILABILITY_NOTIFY_SEND_FAILED order_id=%s admin_id=%s",
                    order.id,
                    admin_id,
                )

        WebsiteLeadService._set_order_meta(
            order,
            product_id=product.id or 0,
            requested_at=now,
            notified_at=now,
        )
        order.updated_at = now
        session.add(order)
        await session.commit()
