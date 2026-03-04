import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from core.config import settings
from models.order import Order, OrderProductLink
from services.bot_service import BotService

logger = logging.getLogger(__name__)


class NotificationService:
    @staticmethod
    async def notify_admins_new_order(
        session: AsyncSession,
        order_id: int,
        *,
        customer_name: str | None = None,
        customer_username: str | None = None,
        customer_phone: str | None = None,
    ) -> None:
        if not settings.admin_list:
            return

        stmt = (
            select(Order)
            .where(Order.id == order_id)
            .options(selectinload(Order.product_links).selectinload(OrderProductLink.product))
        )
        result = await session.execute(stmt)
        order = result.scalar_one_or_none()
        if not order:
            logger.warning("NOTIFY_NEW_ORDER_SKIPPED missing_order_id=%s", order_id)
            return

        message_lines = [
            f"🔔 <b>НОВЫЙ ЗАКАЗ #{order.id}</b>",
            f"👤 {customer_name or 'Без имени'} (@{customer_username or 'без username'})",
            f"📱 {customer_phone or order.delivery_address or 'не указан'}",
            "",
            "🛒 <b>Товары:</b>",
        ]

        for link in order.product_links:
            product_name = link.product.title if link.product else f"Product #{link.product_id}"
            line_total = link.price * link.quantity
            message_lines.append(f"▫️ {product_name} x{link.quantity} — {line_total} р.")
            if link.is_installation_included:
                install_price = link.installation_price or 0
                message_lines.append(f"   └ 🔧 Монтаж: {install_price} BYN")

        message_lines.append("")
        message_lines.append(f"💰 <b>Итого: {order.total_amount} руб.</b>")
        admin_text = "\n".join(message_lines)

        for admin_id in settings.admin_list:
            await BotService.send_message(admin_id, admin_text)
