import logging
from html import escape

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from core.config import settings
from models.order import BankReceipt, Order, OrderProductLink
from services.bot_service import BotService

logger = logging.getLogger(__name__)


class NotificationService:
    @staticmethod
    async def notify_admins_new_order(
        session: AsyncSession,
        order_id: int,
        customer_name: str | None,
        customer_username: str | None,
        customer_phone: str | None,
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
            try:
                await BotService.send_message(admin_id, admin_text)
            except Exception:
                logger.exception("NOTIFY_NEW_ORDER_SEND_FAILED order_id=%s admin_id=%s", order.id, admin_id)

    @staticmethod
    async def notify_admins_bank_receipts_imported(
        session: AsyncSession,
        receipt_ids: list[int],
    ) -> int:
        if not settings.admin_list or not receipt_ids:
            return 0

        stmt = (
            select(BankReceipt)
            .where(BankReceipt.id.in_(receipt_ids))
            .order_by(BankReceipt.received_at.desc(), BankReceipt.created_at.desc())
        )
        result = await session.execute(stmt)
        receipts = list(result.scalars().all())
        if not receipts:
            return 0

        review_count = len([item for item in receipts if item.status == "requires_review"])
        matched_count = len([item for item in receipts if item.status == "matched"])
        lines = [
            f"🔔 <b>Новые банковские поступления: {len(receipts)}</b>",
        ]
        if matched_count:
            lines.append(f"✅ Разнесено автоматически: {matched_count}")
        if review_count:
            lines.append(f"⚠️ Требует проверки: {review_count}")
        lines.append("")
        for receipt in receipts[:10]:
            meta = receipt.match_meta or {}
            candidate_ids = meta.get("candidate_order_ids") or []
            candidate_text = ", ".join(f"#{order_id}" for order_id in candidate_ids[:5]) or "нет"
            amount = f"{receipt.amount:g} {receipt.currency.value if hasattr(receipt.currency, 'value') else receipt.currency}"
            payer = receipt.payer_name or "плательщик не распознан"
            purpose = (receipt.payment_purpose or "").strip()
            if len(purpose) > 180:
                purpose = f"{purpose[:177]}..."
            if receipt.status == "matched":
                status_text = (
                    f"разнесено в заказ #{receipt.matched_order_id}"
                    if receipt.matched_order_id
                    else "разнесено автоматически"
                )
            elif receipt.status == "requires_review":
                status_text = "требует проверки"
            else:
                status_text = receipt.status or "новый"
            lines.extend(
                [
                    f"💳 <b>{escape(amount)}</b> от {escape(payer)}",
                    f"Статус: {escape(status_text)}",
                    f"УНП: {escape(receipt.payer_unp or 'не найден')}",
                    f"Кандидаты заказов: {escape(candidate_text)}",
                ]
            )
            if receipt.payment_document_number:
                lines.append(f"Платежный документ: {escape(receipt.payment_document_number)}")
            if purpose:
                lines.append(f"<i>{escape(purpose)}</i>")
            lines.append("")

        if len(receipts) > 10:
            lines.append(f"Еще {len(receipts) - 10} поступлений видно на главной менеджера.")

        text = "\n".join(lines).strip()
        sent = 0
        for admin_id in settings.admin_list:
            try:
                await BotService.send_message(admin_id, text)
                sent += 1
            except Exception:
                logger.exception("NOTIFY_BANK_RECEIPTS_SEND_FAILED admin_id=%s", admin_id)
        return sent

    notify_admins_bank_receipts_requires_review = notify_admins_bank_receipts_imported
