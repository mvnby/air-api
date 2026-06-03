"""Service-layer orchestration for website lead capture flows."""

import logging
from datetime import datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlalchemy.orm.attributes import flag_modified
from sqlmodel import select

from crud.product import ProductDAO
from models import LeadSource, Order, OrderStatus, Product
from schemas import ProductAvailabilityLeadPayload, ProductAvailabilityLeadResponse
from services.bot_service import BotService
from services.lead_service import LeadService
from services.order_service import OrderService
from services.staff_user_service import StaffUserService

logger = logging.getLogger(__name__)


class WebsiteLeadService:
    PRODUCT_AVAILABILITY_LOOKBACK_DAYS = 14
    PRODUCT_AVAILABILITY_NOTIFY_COOLDOWN_HOURS = 24

    @staticmethod
    async def create_product_availability_lead(
        session: AsyncSession,
        payload: ProductAvailabilityLeadPayload,
    ) -> ProductAvailabilityLeadResponse:
        product = await ProductDAO.get_by_id(session, payload.product_id)
        if not product or not product.is_published:
            raise LookupError(f"Product with id={payload.product_id} not found")

        now = datetime.now()
        existing_order = await WebsiteLeadService._find_recent_product_availability_order(
            session=session,
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
            if should_notify:
                await WebsiteLeadService._notify_admins(
                    session=session,
                    order=order,
                    product=product,
                    payload=payload,
                    now=now,
                    is_repeat=True,
                )
            return ProductAvailabilityLeadResponse(
                lead_id=int(order.id or 0),
                status=str(order.status.value if hasattr(order.status, "value") else order.status),
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
        )
        WebsiteLeadService._set_order_meta(
            order,
            product_id=product.id,
            requested_at=now,
            notified_at=now,
        )
        session.add(order)
        await session.commit()
        await session.refresh(order, ["customer"])

        await WebsiteLeadService._notify_admins(
            session=session,
            order=order,
            product=product,
            payload=payload,
            now=now,
            is_repeat=False,
        )

        return ProductAvailabilityLeadResponse(
            lead_id=int(order.id or 0),
            status=str(order.status.value if hasattr(order.status, "value") else order.status),
            created_at=order.created_at,
        )

    @staticmethod
    def _build_request_text(product: Product) -> str:
        return f"Сообщить о поступлении: {product.title} (slug: {product.slug}, product_id: {product.id})"

    @staticmethod
    async def _find_recent_product_availability_order(
        session: AsyncSession,
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
        await session.commit()
        await session.refresh(order, ["customer"])
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
    ) -> None:
        admin_ids = await StaffUserService.get_active_owner_admin_telegram_recipient_ids(session)
        if not admin_ids:
            return

        message_lines = [
            "🔔 <b>ПОВТОРНЫЙ ЗАПРОС НА ПОСТУПЛЕНИЕ</b>" if is_repeat else "🔔 <b>ЗАПРОС НА ПОСТУПЛЕНИЕ С САЙТА</b>",
            f"🆔 Заявка #{order.id}",
            f"📦 {product.title}",
            f"🔗 /product/{product.slug}",
            f"📱 {payload.phone}",
        ]
        if payload.name and payload.name.strip():
            message_lines.insert(4, f"👤 {payload.name.strip()}")

        admin_text = "\n".join(message_lines)
        for admin_id in admin_ids:
            try:
                await BotService.send_message(admin_id, admin_text)
            except Exception as exc:
                logger.warning(
                    "Failed to notify admin %s about product availability order %s: %s",
                    admin_id,
                    order.id,
                    exc,
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
