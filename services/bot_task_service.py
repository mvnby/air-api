import logging
from datetime import datetime, timedelta
from html import escape
from typing import Any

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Order, OrderInstaller, OrderStageStatus, OrderWorkStage, StaffUser
from services.notification_service import NotificationService
from services.staff_user_service import StaffUserService

logger = logging.getLogger(__name__)


class BotTaskService:
    @staticmethod
    async def _staff_by_telegram_id(session: AsyncSession, telegram_id: int | str | None) -> StaffUser | None:
        try:
            normalized_telegram_id = int(telegram_id) if telegram_id is not None else 0
        except (TypeError, ValueError):
            return None
        if not normalized_telegram_id:
            return None
        result = await session.execute(
            select(StaffUser)
            .where(StaffUser.telegram_id == normalized_telegram_id)
            .where(StaffUser.status == StaffUserService.STATUS_ACTIVE)
        )
        return result.scalars().first()

    @classmethod
    async def list_my_tasks(
        cls,
        session: AsyncSession,
        telegram_id: int | str | None,
        *,
        limit: int = 10,
    ) -> list[dict[str, Any]]:
        staff = await cls._staff_by_telegram_id(session, telegram_id)
        if not staff or not staff.legacy_installer_id:
            return []

        now = datetime.now() - timedelta(days=1)
        until = datetime.now() + timedelta(days=30)
        installer_id = int(staff.legacy_installer_id)

        stage_result = await session.execute(
            select(OrderWorkStage)
            .join(Order, Order.id == OrderWorkStage.order_id)
            .where(OrderWorkStage.installer_id == installer_id)
            .where(
                or_(
                    OrderWorkStage.start_time.is_(None),
                    (OrderWorkStage.start_time >= now) & (OrderWorkStage.start_time <= until),
                )
            )
            .where(OrderWorkStage.status != OrderStageStatus.COMPLETED)
            .where(OrderWorkStage.status != OrderStageStatus.CANCELED)
            .options(
                selectinload(OrderWorkStage.order).selectinload(Order.customer),
                selectinload(OrderWorkStage.installer),
            )
            .order_by(OrderWorkStage.start_time.asc().nullslast(), OrderWorkStage.id.asc())
            .limit(limit)
        )
        tasks = [cls._map_stage(stage) for stage in stage_result.scalars().all()]
        if tasks:
            return tasks

        order_result = await session.execute(
            select(Order)
            .join(OrderInstaller, OrderInstaller.order_id == Order.id)
            .where(OrderInstaller.installer_id == installer_id)
            .where(
                or_(
                    Order.installation_date.is_(None),
                    (Order.installation_date >= now) & (Order.installation_date <= until),
                )
            )
            .options(selectinload(Order.customer), selectinload(Order.installers))
            .order_by(Order.installation_date.asc().nullslast(), Order.id.asc())
            .limit(limit)
        )
        return [cls._map_order(order) for order in order_result.scalars().all()]

    @staticmethod
    def _customer_phone(order: Order) -> str | None:
        customer = getattr(order, "customer", None)
        return getattr(customer, "phone", None) if customer else None

    @staticmethod
    def _customer_name(order: Order) -> str:
        customer = getattr(order, "customer", None)
        return getattr(customer, "name", None) or "Клиент"

    @classmethod
    def _map_stage(cls, stage: OrderWorkStage) -> dict[str, Any]:
        order = stage.order
        return {
            "kind": "stage",
            "id": int(stage.id or 0),
            "order_id": int(stage.order_id),
            "title": stage.name,
            "status": stage.status.value if hasattr(stage.status, "value") else str(stage.status),
            "start_time": stage.start_time,
            "address": order.delivery_address if order else None,
            "customer_name": cls._customer_name(order) if order else "Клиент",
            "customer_phone": cls._customer_phone(order) if order else None,
            "comment": stage.manager_comment,
        }

    @classmethod
    def _map_order(cls, order: Order) -> dict[str, Any]:
        return {
            "kind": "order",
            "id": int(order.id or 0),
            "order_id": int(order.id or 0),
            "title": order.title or "Монтаж",
            "status": order.status.value if hasattr(order.status, "value") else str(order.status),
            "start_time": order.installation_date,
            "address": order.delivery_address,
            "customer_name": cls._customer_name(order),
            "customer_phone": cls._customer_phone(order),
            "comment": order.comment,
        }

    @staticmethod
    def format_tasks(tasks: list[dict[str, Any]]) -> str:
        if not tasks:
            return "У вас нет ближайших задач."
        lines = ["<b>Мои ближайшие задачи</b>"]
        for task in tasks:
            dt = task.get("start_time")
            date_text = dt.strftime("%d.%m.%Y %H:%M") if dt else "время не назначено"
            lines.extend(
                [
                    "",
                    f"<b>#{task['order_id']} - {escape(str(task['title']))}</b>",
                    f"Дата: {escape(date_text)}",
                    f"Клиент: {escape(str(task.get('customer_name') or 'Клиент'))}",
                    f"Телефон: {escape(str(task.get('customer_phone') or 'не указан'))}",
                    f"Адрес: {escape(str(task.get('address') or 'не указан'))}",
                ]
            )
            if task.get("comment"):
                lines.append(f"Комментарий: {escape(str(task['comment']))}")
        return "\n".join(lines)

    @staticmethod
    def format_tasks_rich_html(tasks: list[dict[str, Any]]) -> str:
        if not tasks:
            return "<h3>Мои ближайшие задачи</h3><p>У вас нет ближайших задач.</p>"

        blocks = ["<h3>Мои ближайшие задачи</h3>"]
        for task in tasks:
            dt = task.get("start_time")
            date_text = dt.strftime("%d.%m.%Y %H:%M") if dt else "время не назначено"
            blocks.append(
                "<p>"
                f"<b>#{task['order_id']} - {escape(str(task['title']))}</b><br/>"
                f"<b>Дата:</b> {escape(date_text)}<br/>"
                f"<b>Клиент:</b> {escape(str(task.get('customer_name') or 'Клиент'))}<br/>"
                f"<b>Телефон:</b> {escape(str(task.get('customer_phone') or 'не указан'))}<br/>"
                f"<b>Адрес:</b> {escape(str(task.get('address') or 'не указан'))}"
                "</p>"
            )
            if task.get("comment"):
                blocks.append(f"<blockquote>{escape(str(task['comment']))}</blockquote>")
        return "".join(blocks)

    @staticmethod
    def build_stage_report(
        *,
        text: str | None = None,
        caption: str | None = None,
        photo_file_id: str | None = None,
        document_file_id: str | None = None,
        document_name: str | None = None,
    ) -> str:
        body = (text or caption or "").strip()
        lines: list[str] = [body] if body else []
        attachments: list[str] = []

        if photo_file_id:
            attachments.append(f"Фото: {photo_file_id}")

        if document_file_id:
            safe_name = " ".join((document_name or "файл").split())[:120] or "файл"
            attachments.append(f"Документ: {safe_name} ({document_file_id})")

        if attachments:
            if lines:
                lines.append("")
            lines.append("Вложения:")
            lines.extend(f"- {attachment}" for attachment in attachments)

        return "\n".join(lines).strip()

    @staticmethod
    async def update_stage_status(
        session: AsyncSession,
        stage_id: int,
        status: str,
        *,
        telegram_id: int | str | None,
    ) -> bool:
        staff = await BotTaskService._staff_by_telegram_id(session, telegram_id)
        stage = await session.get(OrderWorkStage, stage_id)
        if not staff or not stage or stage.installer_id != staff.legacy_installer_id:
            return False
        stage.status = OrderStageStatus(status)
        session.add(stage)
        await session.commit()
        try:
            await NotificationService.notify_admins_work_stage_status_changed(session, stage_id)
        except Exception:
            logger.exception("BOT_TASK_STATUS_NOTIFY_FAILED stage_id=%s", stage_id)
        return True

    @staticmethod
    async def save_stage_report(
        session: AsyncSession,
        stage_id: int,
        report: str,
        *,
        telegram_id: int | str | None,
    ) -> bool:
        staff = await BotTaskService._staff_by_telegram_id(session, telegram_id)
        stage = await session.get(OrderWorkStage, stage_id)
        if not staff or not stage or stage.installer_id != staff.legacy_installer_id:
            return False
        stage.installer_report = report.strip()
        session.add(stage)
        await session.commit()
        return True
