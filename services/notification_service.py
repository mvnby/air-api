import logging

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Customer
from models.order import BankReceipt, Order, OrderProductLink, OrderWorkStage
from models.tenancy import TenantScope
from services.bot_service import BotService
from services.staff_user_service import StaffUserService
from services.tenant_entity_access_service import TenantEntityAccessService

logger = logging.getLogger(__name__)


class NotificationService:
    # A single Telegram message is limited to 4096 characters. Detailed bank
    # and email entries are intentionally capped so bounded-but-long database
    # values cannot make the whole notification undeliverable.
    MAX_DETAILED_BATCH_ITEMS = 4

    SERVICE_LABELS = {
        "turnkey": "Продажа + монтаж",
        "install_only": "Монтаж",
        "pre_install": "Закладка трассы",
        "maintenance": "Обслуживание",
        "repair": "Ремонт",
        "dismantling": "Демонтаж",
    }
    WORK_STAGE_STATUS_LABELS = {
        "planned": "запланирована",
        "in_progress": "принята в работу",
        "completed": "выполнена",
        "canceled": "отменена",
    }

    @staticmethod
    async def _admin_recipient_ids(
        session: AsyncSession,
        *,
        tenant_scope: TenantScope,
    ) -> list[int]:
        return await StaffUserService.get_active_owner_admin_telegram_recipient_ids(
            session,
            tenant_scope=tenant_scope,
        )

    @staticmethod
    async def notify_admins_new_order(
        session: AsyncSession,
        order_id: int,
        customer_name: str | None,
        customer_username: str | None,
        customer_phone: str | None,
        *,
        tenant_scope: TenantScope,
    ) -> None:
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
            options=(
                selectinload(Order.product_links).selectinload(
                    OrderProductLink.product
                ),
            ),
        )
        if not order:
            logger.warning("NOTIFY_NEW_ORDER_SKIPPED missing_order_id=%s", order_id)
            return
        admin_ids = await NotificationService._admin_recipient_ids(
            session,
            tenant_scope=tenant_scope,
        )
        if not admin_ids:
            return

        message_lines = [
            f"🔔 <b>НОВЫЙ ЗАКАЗ #{order.id}</b>",
            f"👤 {BotService.escape_html(customer_name or 'Без имени', max_length=160)} "
            f"(@{BotService.escape_html(customer_username or 'без username', max_length=80)})",
            f"📱 {BotService.escape_html(customer_phone or order.delivery_address or 'не указан', max_length=180)}",
            "",
            "🛒 <b>Товары:</b>",
        ]

        product_links = list(order.product_links or [])
        for link in product_links[:10]:
            product_name = link.product.title if link.product else f"Product #{link.product_id}"
            line_total = link.price * link.quantity
            message_lines.append(
                f"▫️ {BotService.escape_html(product_name, max_length=140)} "
                f"x{link.quantity} — {line_total} р."
            )
            if link.is_installation_included:
                install_price = link.installation_price or 0
                message_lines.append(f"   └ 🔧 Монтаж: {install_price} BYN")

        if len(product_links) > 10:
            message_lines.append(f"… ещё товаров: {len(product_links) - 10}")

        message_lines.append("")
        message_lines.append(f"💰 <b>Итого: {order.total_amount} руб.</b>")
        admin_text = "\n".join(message_lines)

        for admin_id in admin_ids:
            try:
                delivered = await BotService.send_message(admin_id, admin_text)
                if not delivered:
                    logger.warning(
                        "NOTIFY_NEW_ORDER_DELIVERY_FAILED order_id=%s admin_id=%s",
                        order.id,
                        admin_id,
                    )
            except Exception:
                logger.exception("NOTIFY_NEW_ORDER_SEND_FAILED order_id=%s admin_id=%s", order.id, admin_id)

    @staticmethod
    async def notify_admins_staff_order_created(
        session: AsyncSession,
        order_id: int,
        *,
        source_label: str = "рабочий бот",
        tenant_scope: TenantScope,
    ) -> int:
        order = await TenantEntityAccessService.get_order(
            session,
            order_id,
            tenant_scope=tenant_scope,
            options=(selectinload(Order.customer),),
        )
        if not order:
            logger.warning("NOTIFY_STAFF_ORDER_SKIPPED missing_order_id=%s", order_id)
            return 0
        admin_ids = await NotificationService._admin_recipient_ids(
            session,
            tenant_scope=tenant_scope,
        )
        if not admin_ids:
            return 0

        customer = getattr(order, "customer", None)
        customer_name = getattr(customer, "name", None) or "Новый клиент"
        customer_phone = getattr(customer, "phone", None) or "не указан"
        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        service_type = str(meta.get("service_type") or "").strip()
        service_label = NotificationService.SERVICE_LABELS.get(service_type, service_type or "не указана")
        order_date = order.installation_date or order.measurement_date
        date_text = order_date.strftime("%d.%m.%Y %H:%M") if order_date else "не назначена"
        comment = (order.comment or "").strip()
        if len(comment) > 320:
            comment = f"{comment[:317]}..."

        lines = [
            f"🔔 <b>Новый рабочий заказ #{order.id}</b>",
            f"Источник: {BotService.escape_html(source_label, max_length=100)}",
            f"Услуга: {BotService.escape_html(service_label, max_length=140)}",
            f"Дата: {BotService.escape_html(date_text, max_length=80)}",
            f"Клиент: {BotService.escape_html(customer_name, max_length=160)}",
            f"Телефон: {BotService.escape_html(customer_phone, max_length=80)}",
            f"Адрес: {BotService.escape_html(order.delivery_address or 'не указан', max_length=300)}",
        ]
        if comment:
            lines.extend(["", f"<i>{BotService.escape_html(comment, max_length=320)}</i>"])

        text = "\n".join(lines)
        rich_html = (
            f"<h3>Новый рабочий заказ #{order.id}</h3>"
            "<p>"
            f"<b>Источник:</b> {BotService.escape_html(source_label, max_length=100)}<br/>"
            f"<b>Услуга:</b> {BotService.escape_html(service_label, max_length=140)}<br/>"
            f"<b>Дата:</b> {BotService.escape_html(date_text, max_length=80)}<br/>"
            f"<b>Клиент:</b> {BotService.escape_html(customer_name, max_length=160)}<br/>"
            f"<b>Телефон:</b> {BotService.escape_html(customer_phone, max_length=80)}<br/>"
            f"<b>Адрес:</b> {BotService.escape_html(order.delivery_address or 'не указан', max_length=300)}"
            "</p>"
        )
        if comment:
            rich_html += f"<blockquote>{BotService.escape_html(comment, max_length=320)}</blockquote>"

        sent = 0
        for admin_id in admin_ids:
            try:
                delivered = await BotService.send_rich_message(
                    admin_id,
                    rich_html,
                    fallback_text=text,
                )
                if delivered:
                    sent += 1
                else:
                    logger.warning(
                        "NOTIFY_STAFF_ORDER_DELIVERY_FAILED order_id=%s admin_id=%s",
                        order.id,
                        admin_id,
                    )
            except Exception:
                logger.exception("NOTIFY_STAFF_ORDER_SEND_FAILED order_id=%s admin_id=%s", order.id, admin_id)
        return sent

    @staticmethod
    async def notify_admins_work_stage_status_changed(
        session: AsyncSession,
        stage_id: int,
        *,
        tenant_scope: TenantScope,
    ) -> int:
        stage = await TenantEntityAccessService.get_order_stage(
            session,
            stage_id,
            tenant_scope=tenant_scope,
            options=(
                selectinload(OrderWorkStage.order).selectinload(Order.customer),
                selectinload(OrderWorkStage.installer),
            ),
        )
        if not stage:
            logger.warning("NOTIFY_WORK_STAGE_STATUS_SKIPPED missing_stage_id=%s", stage_id)
            return 0
        admin_ids = await NotificationService._admin_recipient_ids(
            session,
            tenant_scope=tenant_scope,
        )
        if not admin_ids:
            return 0

        order = getattr(stage, "order", None)
        customer = getattr(order, "customer", None) if order else None
        installer = getattr(stage, "installer", None)
        status_value = stage.status.value if hasattr(stage.status, "value") else str(stage.status)
        status_label = NotificationService.WORK_STAGE_STATUS_LABELS.get(status_value, status_value)
        date_text = stage.start_time.strftime("%d.%m.%Y %H:%M") if stage.start_time else "не назначена"
        order_id = getattr(order, "id", None) or stage.order_id
        title = stage.name or "Рабочая задача"
        customer_name = getattr(customer, "name", None) or "Клиент"
        customer_phone = getattr(customer, "phone", None) or "не указан"
        address = getattr(order, "delivery_address", None) if order else None
        installer_name = getattr(installer, "name", None) or "исполнитель не указан"
        comment = (stage.installer_report or stage.manager_comment or "").strip()
        if len(comment) > 320:
            comment = f"{comment[:317]}..."

        text_lines = [
            f"🔧 <b>Задача #{stage.id}: {BotService.escape_html(status_label, max_length=100)}</b>",
            f"Заказ: #{order_id}",
            f"Задача: {BotService.escape_html(title, max_length=180)}",
            f"Исполнитель: {BotService.escape_html(installer_name, max_length=160)}",
            f"Дата: {BotService.escape_html(date_text, max_length=80)}",
            f"Клиент: {BotService.escape_html(customer_name, max_length=160)}",
            f"Телефон: {BotService.escape_html(customer_phone, max_length=80)}",
            f"Адрес: {BotService.escape_html(address or 'не указан', max_length=300)}",
        ]
        if comment:
            text_lines.extend(["", f"<i>{BotService.escape_html(comment, max_length=320)}</i>"])
        text = "\n".join(text_lines)

        rich_html = (
            f"<h3>Задача #{stage.id}: {BotService.escape_html(status_label, max_length=100)}</h3>"
            "<p>"
            f"<b>Заказ:</b> #{order_id}<br/>"
            f"<b>Задача:</b> {BotService.escape_html(title, max_length=180)}<br/>"
            f"<b>Исполнитель:</b> {BotService.escape_html(installer_name, max_length=160)}<br/>"
            f"<b>Дата:</b> {BotService.escape_html(date_text, max_length=80)}<br/>"
            f"<b>Клиент:</b> {BotService.escape_html(customer_name, max_length=160)}<br/>"
            f"<b>Телефон:</b> {BotService.escape_html(customer_phone, max_length=80)}<br/>"
            f"<b>Адрес:</b> {BotService.escape_html(address or 'не указан', max_length=300)}"
            "</p>"
        )
        if comment:
            rich_html += f"<blockquote>{BotService.escape_html(comment, max_length=320)}</blockquote>"

        sent = 0
        for admin_id in admin_ids:
            try:
                delivered = await BotService.send_rich_message(
                    admin_id,
                    rich_html,
                    fallback_text=text,
                )
                if delivered:
                    sent += 1
                else:
                    logger.warning(
                        "NOTIFY_WORK_STAGE_STATUS_DELIVERY_FAILED stage_id=%s admin_id=%s",
                        stage.id,
                        admin_id,
                    )
            except Exception:
                logger.exception(
                    "NOTIFY_WORK_STAGE_STATUS_SEND_FAILED stage_id=%s admin_id=%s",
                    stage.id,
                    admin_id,
                )
        return sent

    @staticmethod
    async def notify_admins_bank_receipts_imported(
        session: AsyncSession,
        receipt_ids: list[int],
        *,
        tenant_scope: TenantScope,
    ) -> int:
        if not tenant_scope.is_system:
            logger.warning(
                "NOTIFY_BANK_RECEIPTS_SKIPPED non_system_tenant_id=%s",
                tenant_scope.tenant_id,
            )
            return 0
        admin_ids = await NotificationService._admin_recipient_ids(
            session,
            tenant_scope=tenant_scope,
        )
        if not admin_ids or not receipt_ids:
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
        visible_receipts = receipts[: NotificationService.MAX_DETAILED_BATCH_ITEMS]
        for receipt in visible_receipts:
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
            elif receipt.status == "closed_orders":
                status_text = "оплата закрытых заказов"
            elif receipt.status == "non_order_income":
                status_text = "не относится к заказам"
            else:
                status_text = receipt.status or "новый"
            lines.extend(
                [
                    f"💳 <b>{BotService.escape_html(amount, max_length=80)}</b> от "
                    f"{BotService.escape_html(payer, max_length=180)}",
                    f"Статус: {BotService.escape_html(status_text, max_length=120)}",
                    f"УНП: {BotService.escape_html(receipt.payer_unp or 'не найден', max_length=80)}",
                    f"Кандидаты заказов: {BotService.escape_html(candidate_text, max_length=160)}",
                ]
            )
            if receipt.payment_document_number:
                lines.append(
                    "Платежный документ: "
                    f"{BotService.escape_html(receipt.payment_document_number, max_length=100)}"
                )
            if purpose:
                lines.append(f"<i>{BotService.escape_html(purpose, max_length=180)}</i>")
            lines.append("")

        if len(receipts) > len(visible_receipts):
            lines.append(
                f"Еще {len(receipts) - len(visible_receipts)} поступлений видно на главной менеджера."
            )

        text = "\n".join(lines).strip()
        sent = 0
        for admin_id in admin_ids:
            try:
                delivered = await BotService.send_message(admin_id, text)
                if delivered:
                    sent += 1
                else:
                    logger.warning("NOTIFY_BANK_RECEIPTS_DELIVERY_FAILED admin_id=%s", admin_id)
            except Exception:
                logger.exception("NOTIFY_BANK_RECEIPTS_SEND_FAILED admin_id=%s", admin_id)
        return sent

    notify_admins_bank_receipts_requires_review = notify_admins_bank_receipts_imported

    @staticmethod
    async def notify_admins_email_leads_imported(
        session: AsyncSession,
        order_ids: list[int],
        *,
        tenant_scope: TenantScope,
    ) -> int:
        admin_ids = await NotificationService._admin_recipient_ids(
            session,
            tenant_scope=tenant_scope,
        )
        if not admin_ids or not order_ids:
            return 0

        stmt = (
            select(Order)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(
                Order.id.in_(order_ids),
                TenantEntityAccessService.order_clause(tenant_scope),
                TenantEntityAccessService.order_customer_clause(tenant_scope),
            )
            .order_by(Order.created_at.desc())
        )
        result = await session.execute(stmt)
        orders = list(result.scalars().all())
        if not orders:
            return 0

        lines = [f"🔔 <b>Новые email-заказы: {len(orders)}</b>", ""]
        visible_orders = orders[: NotificationService.MAX_DETAILED_BATCH_ITEMS]
        for order in visible_orders:
            meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
            sender = str(meta.get("email_sender") or "отправитель не распознан")
            subject = str(meta.get("email_subject") or "без темы")
            reason = str(meta.get("email_ai_reason") or "").strip()
            comment = (order.comment or "").strip()
            if len(comment) > 220:
                comment = f"{comment[:217]}..."
            if len(reason) > 180:
                reason = f"{reason[:177]}..."

            lines.extend(
                [
                    f"📩 <b>Заказ #{order.id}</b>",
                    f"От: {BotService.escape_html(sender, max_length=160)}",
                    f"Тема: {BotService.escape_html(subject, max_length=220)}",
                ]
            )
            if reason:
                lines.append(f"AI: {BotService.escape_html(reason, max_length=180)}")
            if comment:
                lines.append(f"<i>{BotService.escape_html(comment, max_length=220)}</i>")
            lines.append("")

        if len(orders) > len(visible_orders):
            lines.append(
                f"Еще {len(orders) - len(visible_orders)} email-заказов видно в менеджере."
            )

        text = "\n".join(lines).strip()
        sent = 0
        for admin_id in admin_ids:
            try:
                delivered = await BotService.send_message(admin_id, text)
                if delivered:
                    sent += 1
                else:
                    logger.warning("NOTIFY_EMAIL_LEADS_DELIVERY_FAILED admin_id=%s", admin_id)
            except Exception:
                logger.exception("NOTIFY_EMAIL_LEADS_SEND_FAILED admin_id=%s", admin_id)
        return sent
