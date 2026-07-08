from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import Customer, Order, OutgoingEmail
from services.mail_smtp_service import MailSmtpService


OUTGOING_EMAIL_STATUSES = {"pending", "sent", "failed"}


class OutgoingEmailService:
    @staticmethod
    def _apply_filters(
        stmt,
        *,
        status: Optional[str] = None,
        order_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        recipient: Optional[str] = None,
        q: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ):
        if status:
            stmt = stmt.where(OutgoingEmail.status == status)
        if order_id:
            stmt = stmt.where(OutgoingEmail.order_id == order_id)
        if customer_id:
            stmt = stmt.where(OutgoingEmail.customer_id == customer_id)
        if recipient:
            stmt = stmt.where(OutgoingEmail.recipient_email.ilike(f"%{recipient.strip()}%"))
        if q:
            query = f"%{q.strip()}%"
            stmt = stmt.where(
                or_(
                    OutgoingEmail.subject.ilike(query),
                    OutgoingEmail.recipient_email.ilike(query),
                    OutgoingEmail.error.ilike(query),
                )
            )
        if date_from:
            stmt = stmt.where(OutgoingEmail.created_at >= date_from)
        if date_to:
            stmt = stmt.where(OutgoingEmail.created_at <= date_to)
        return stmt

    @staticmethod
    def _serialize(row: OutgoingEmail, customer_name: Optional[str] = None, order_title: Optional[str] = None) -> Dict[str, Any]:
        return {
            "id": row.id,
            "status": row.status,
            "retry_of_email_id": row.retry_of_email_id,
            "order_id": row.order_id,
            "customer_id": row.customer_id,
            "customer_name": customer_name,
            "order_title": order_title,
            "recipient_email": row.recipient_email,
            "subject": row.subject,
            "body_text": row.body_text,
            "body_html": row.body_html,
            "from_email": row.from_email,
            "from_name": row.from_name,
            "reply_to": row.reply_to,
            "attachments": row.attachments,
            "error": row.error,
            "sent_at": row.sent_at,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    @staticmethod
    async def _hydrate_rows(session: AsyncSession, rows: Iterable[OutgoingEmail]) -> List[Dict[str, Any]]:
        row_list = list(rows)
        if not row_list:
            return []

        customer_ids = sorted({row.customer_id for row in row_list if row.customer_id})
        order_ids = sorted({row.order_id for row in row_list if row.order_id})

        customers: Dict[int, str] = {}
        if customer_ids:
            result = await session.execute(select(Customer.id, Customer.name).where(Customer.id.in_(customer_ids)))
            customers = {int(customer_id): name for customer_id, name in result.all()}

        orders: Dict[int, str] = {}
        if order_ids:
            result = await session.execute(select(Order.id, Order.title).where(Order.id.in_(order_ids)))
            orders = {int(order_id): title or f"Заказ #{order_id}" for order_id, title in result.all()}

        return [
            OutgoingEmailService._serialize(
                row,
                customer_name=customers.get(row.customer_id or 0),
                order_title=orders.get(row.order_id or 0),
            )
            for row in row_list
        ]

    @classmethod
    async def list_emails(
        cls,
        session: AsyncSession,
        *,
        page: int = 1,
        limit: int = 50,
        status: Optional[str] = None,
        order_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        recipient: Optional[str] = None,
        q: Optional[str] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        if status and status not in OUTGOING_EMAIL_STATUSES:
            raise ValueError("Unknown outgoing email status")

        base = cls._apply_filters(
            select(OutgoingEmail),
            status=status,
            order_id=order_id,
            customer_id=customer_id,
            recipient=recipient,
            q=q,
            date_from=date_from,
            date_to=date_to,
        )
        count_stmt = cls._apply_filters(
            select(func.count()).select_from(OutgoingEmail),
            status=status,
            order_id=order_id,
            customer_id=customer_id,
            recipient=recipient,
            q=q,
            date_from=date_from,
            date_to=date_to,
        )
        total = int((await session.execute(count_stmt)).scalar_one() or 0)
        result = await session.execute(
            base.order_by(OutgoingEmail.created_at.desc(), OutgoingEmail.id.desc())
            .offset((page - 1) * limit)
            .limit(limit)
        )
        items = await cls._hydrate_rows(session, result.scalars().all())
        return items, total

    @classmethod
    async def get_email_detail(cls, session: AsyncSession, email_id: int) -> Dict[str, Any]:
        email = await session.get(OutgoingEmail, email_id)
        if not email:
            raise ValueError("Outgoing email not found")

        item = (await cls._hydrate_rows(session, [email]))[0]
        root_id = email.retry_of_email_id or email.id
        attempts_result = await session.execute(
            select(OutgoingEmail)
            .where(or_(OutgoingEmail.id == root_id, OutgoingEmail.retry_of_email_id == root_id))
            .order_by(OutgoingEmail.created_at.asc(), OutgoingEmail.id.asc())
        )
        item["retry_attempts"] = await cls._hydrate_rows(session, attempts_result.scalars().all())
        return item

    @classmethod
    async def retry_failed_email(cls, session: AsyncSession, email_id: int) -> Dict[str, Any]:
        original = await session.get(OutgoingEmail, email_id)
        if not original:
            raise ValueError("Outgoing email not found")
        if original.status != "failed":
            raise ValueError("Only failed emails can be retried")

        retry_root_id = original.retry_of_email_id or original.id
        retry = OutgoingEmail(
            status="pending",
            retry_of_email_id=retry_root_id,
            order_id=original.order_id,
            customer_id=original.customer_id,
            recipient_email=original.recipient_email,
            subject=original.subject,
            body_text=original.body_text,
            body_html=original.body_html,
            from_email=MailSmtpService._configured_from_email() or original.from_email,
            from_name=original.from_name,
            reply_to=original.reply_to,
            attachments=original.attachments,
        )
        session.add(retry)
        await session.flush()

        try:
            if original.attachments:
                raise RuntimeError(
                    "Повторная отправка письма с вложениями недоступна без snapshot PDF. "
                    "Отправьте документы заново из заказа."
                )
            message = MailSmtpService.build_message(
                to_email=retry.recipient_email,
                subject=retry.subject,
                body_text=retry.body_text,
                body_html=retry.body_html,
                reply_to=retry.reply_to,
                attachments=[],
            )
            MailSmtpService.send_message(message)
        except Exception as exc:
            retry.status = "failed"
            retry.error = MailSmtpService._sanitize_error(exc)
            session.add(retry)
            await session.commit()
            await session.refresh(retry)
            return (await cls._hydrate_rows(session, [retry]))[0]

        retry.status = "sent"
        retry.error = None
        retry.sent_at = datetime.now()
        session.add(retry)
        await session.commit()
        await session.refresh(retry)
        return (await cls._hydrate_rows(session, [retry]))[0]
