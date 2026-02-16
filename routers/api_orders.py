"""Public order endpoints split from the main API router."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from schemas import OrderPayload, OrderResponse

router = APIRouter(tags=["api"])
logger = logging.getLogger(__name__)


@router.post("/v1/orders", response_model=OrderResponse, operation_id="create_order")
async def create_order(payload: OrderPayload, session: AsyncSession = Depends(get_session)):
    """
    Create a new order from website.
    Accepts customer information and cart items.
    """
    from models import LeadSource
    from services.order_service import OrderService

    logger.info(f"📦 Incoming order payload: customer={payload.customer.name}, items_count={len(payload.items)}")
    for idx, item in enumerate(payload.items):
        logger.info(
            "   Item %s: product_id=%s, qty=%s, with_install=%s, install_price=%s",
            idx,
            item.product_id,
            item.quantity,
            getattr(item, "with_installation", "N/A"),
            getattr(item, "installation_price", "N/A"),
        )

    items = [
        {
            "product_id": item.product_id,
            "quantity": item.quantity,
            "with_installation": item.with_installation,
            "installation_price": item.installation_price,
            "installation_meta": item.installation_meta,
            "installation_options": item.installation_options,
        }
        for item in payload.items
    ]

    order = await OrderService.create_from_website(
        session=session,
        customer_name=payload.customer.name,
        customer_phone=payload.customer.phone,
        customer_email=payload.customer.email,
        customer_address=payload.customer.address,
        items=items,
        lead_source=LeadSource.SITE,
        comment=payload.comment,
        customer_type=payload.customer.type,
        customer_inn=payload.customer.inn,
        customer_legal_name=payload.customer.full_legal_name,
        customer_legal_address=payload.customer.legal_address,
        customer_iban=payload.customer.iban,
        customer_bic=payload.customer.bic,
        customer_bank_name=payload.customer.bank_name,
    )

    from core.config import settings
    from services.bot_service import BotService

    if settings.admin_list:
        await session.refresh(order, ["product_links", "service_links", "customer"])
        for link in order.product_links:
            await session.refresh(link, ["product"])

        message_lines = [
            f"🌐 <b>ЗАКАЗ С САЙТА #{order.id}</b>",
            f"👤 {payload.customer.name}",
            f"📱 {payload.customer.phone}",
        ]

        if payload.customer.email:
            message_lines.append(f"📧 {payload.customer.email}")
        if payload.customer.address:
            message_lines.append(f"📍 {payload.customer.address}")
        if payload.comment:
            message_lines.append(f"💬 {payload.comment}")

        message_lines.append("")
        message_lines.append("🛒 <b>Товары:</b>")

        for link in order.product_links:
            product_name = link.product.title if link.product else f"Product #{link.product_id}"
            line_total = link.price * link.quantity
            message_lines.append(f"▫️ {product_name} x{link.quantity} — {line_total} р.")

            if link.is_installation_included:
                install_price = link.installation_price or 0
                message_lines.append(f"   └ 🔧 Монтаж: {install_price} BYN")

        if order.service_links:
            for s_link in order.service_links:
                title = s_link.title or "Услуга"
                total = s_link.price * s_link.quantity
                message_lines.append(f"🔧 {title} x{s_link.quantity} — {total} BYN")

        message_lines.append("")
        message_lines.append(f"💰 <b>Итого: {order.total_amount} руб.</b>")
        admin_text = "\n".join(message_lines)

        for admin_id in settings.admin_list:
            try:
                await BotService.send_message(admin_id, admin_text)
            except Exception as e:
                logger.warning(f"Failed to notify admin {admin_id}: {e}")

    return OrderResponse(
        id=order.id,
        status=order.status,
        total_amount=order.total_amount,
        created_at=order.created_at,
    )
