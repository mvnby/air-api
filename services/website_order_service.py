"""Service-layer orchestration for website checkout orders."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from models import LeadSource, Order, OrderStatus
from schemas import OrderPayload, OrderResponse
from services.bot_service import BotService
from services.installation_pricing_service import InstallationPricingService
from services.order_service import OrderService
from services.staff_user_service import StaffUserService
from services.tenant_scope_service import TenantScope

logger = logging.getLogger(__name__)


class WebsiteOrderService:
    @staticmethod
    async def create_order(
        session: AsyncSession,
        payload: OrderPayload,
        *,
        tenant_scope: TenantScope,
    ) -> OrderResponse:
        logger.info(
            "PUBLIC_CHECKOUT_RECEIVED item_count=%s installation_item_count=%s",
            len(payload.items),
            len([item for item in payload.items if item.with_installation]),
        )
        items = await InstallationPricingService.price_public_items(session, payload.items)
        pricing_snapshots = [
            {
                "item_index": index,
                "product_id": item["product_id"],
                "quantity": item["quantity"],
                "installation_meta": item["installation_meta"],
            }
            for index, item in enumerate(items)
            if item["with_installation"]
        ]

        order = await OrderService.create_from_website(
            session=session,
            customer_name=payload.customer.name,
            customer_phone=payload.customer.phone,
            customer_email=payload.customer.email,
            customer_address=payload.customer.address,
            items=items,
            lead_source=LeadSource.SITE,
            initial_status=OrderStatus.NEGOTIATION,
            comment=payload.comment,
            customer_type=payload.customer.type,
            customer_inn=payload.customer.inn,
            customer_full_legal_name=payload.customer.full_legal_name,
            customer_legal_address=payload.customer.legal_address,
            customer_iban=payload.customer.iban,
            customer_bic=payload.customer.bic,
            customer_bank_name=payload.customer.bank_name,
            order_technical_meta={
                "public_installation_pricing": {
                    "pricing_version": InstallationPricingService.PRICING_VERSION,
                    "items": pricing_snapshots,
                }
            } if pricing_snapshots else None,
            tenant_scope=tenant_scope,
        )

        await WebsiteOrderService._notify_admins(session, order, payload)

        return OrderResponse(
            id=order.id,
            status=order.status,
            total_amount=order.total_amount,
            created_at=order.created_at,
        )

    @staticmethod
    async def _notify_admins(session: AsyncSession, order: Order, payload: OrderPayload) -> None:
        admin_ids = await StaffUserService.get_active_owner_admin_telegram_recipient_ids(session)
        if not admin_ids:
            return

        await session.refresh(order, ["product_links", "service_links", "customer"])
        for link in order.product_links:
            await session.refresh(link, ["product"])

        message_lines = [
            f"🌐 <b>ЗАКАЗ С САЙТА #{order.id}</b>",
            f"👤 {BotService.escape_html(payload.customer.name, max_length=160)}",
            f"📱 {BotService.escape_html(payload.customer.phone, max_length=80)}",
        ]

        if payload.customer.email:
            message_lines.append(f"📧 {BotService.escape_html(payload.customer.email, max_length=254)}")
        if payload.customer.address:
            message_lines.append(f"📍 {BotService.escape_html(payload.customer.address, max_length=300)}")
        if payload.comment:
            message_lines.append(f"💬 {BotService.escape_html(payload.comment, max_length=500)}")

        message_lines.append("")
        message_lines.append("🛒 <b>Товары:</b>")

        product_links = list(order.product_links or [])
        for link in product_links[:6]:
            product_name = link.product.title if link.product else f"Product #{link.product_id}"
            line_total = link.price * link.quantity
            message_lines.append(
                f"▫️ {BotService.escape_html(product_name, max_length=140)} "
                f"x{link.quantity} — {line_total} р."
            )

            if link.is_installation_included:
                install_price = link.installation_price or 0
                message_lines.append(f"   └ 🔧 Монтаж: {install_price} BYN")

        if len(product_links) > 6:
            message_lines.append(f"… ещё товаров: {len(product_links) - 6}")

        if order.service_links:
            service_links = list(order.service_links)
            for service_link in service_links[:4]:
                title = service_link.title or "Услуга"
                total = service_link.price * service_link.quantity
                message_lines.append(
                    f"🔧 {BotService.escape_html(title, max_length=140)} "
                    f"x{service_link.quantity} — {total} BYN"
                )
            if len(service_links) > 4:
                message_lines.append(f"… ещё услуг: {len(service_links) - 4}")

        message_lines.append("")
        message_lines.append(f"💰 <b>Итого: {order.total_amount} руб.</b>")
        admin_text = "\n".join(message_lines)

        for admin_id in admin_ids:
            try:
                delivered = await BotService.send_message(admin_id, admin_text)
                if not delivered:
                    logger.warning(
                        "WEBSITE_ORDER_NOTIFY_DELIVERY_FAILED order_id=%s admin_id=%s",
                        order.id,
                        admin_id,
                    )
            except Exception:
                logger.exception(
                    "WEBSITE_ORDER_NOTIFY_SEND_FAILED order_id=%s admin_id=%s",
                    order.id,
                    admin_id,
                )
