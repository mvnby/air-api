"""Scoped mail and attachment persistence, without SMTP or business rules."""

from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from models import Customer, Order, OutgoingEmail
from models.mail_workspace import MailAttachmentSnapshot
from models.tenancy import TenantScope


class MailWorkspaceDAO:
    @staticmethod
    def scope_clause(scope: TenantScope):
        clauses = [OutgoingEmail.tenant_id == scope.tenant_id]
        if scope.is_system:
            # Old standalone messages had no company. Never share them with partners.
            clauses.append(OutgoingEmail.tenant_id.is_(None))
        return or_(*clauses)

    @classmethod
    async def get(cls, session: AsyncSession, email_id: int, scope: TenantScope, *, lock: bool = False):
        stmt = select(OutgoingEmail).where(OutgoingEmail.id == email_id, cls.scope_clause(scope)).execution_options(populate_existing=True)
        if lock:
            stmt = stmt.with_for_update()
        return (await session.execute(stmt)).scalar_one_or_none()

    @staticmethod
    async def attachments(session: AsyncSession, email_id: int, tenant_id: int, *, include_content: bool = True):
        statement = select(MailAttachmentSnapshot).where(
            MailAttachmentSnapshot.email_id == email_id,
            MailAttachmentSnapshot.tenant_id == tenant_id,
        ).order_by(MailAttachmentSnapshot.id)
        if not include_content:
            statement = statement.options(defer(MailAttachmentSnapshot.content))
        return list((await session.execute(statement)).scalars().all())

    @staticmethod
    async def attachments_by_email(session, email_ids, tenant_id):
        if not email_ids:
            return {}
        rows = (await session.execute(select(MailAttachmentSnapshot).where(
            MailAttachmentSnapshot.email_id.in_(email_ids), MailAttachmentSnapshot.tenant_id == tenant_id
        ).options(defer(MailAttachmentSnapshot.content)).order_by(MailAttachmentSnapshot.id))).scalars().all()
        grouped = {email_id: [] for email_id in email_ids}
        for row in rows:
            grouped[row.email_id].append(row)
        return grouped

    @classmethod
    async def list(cls, session: AsyncSession, scope: TenantScope, *, folder: str, status: str | None,
                   q: str | None, order_id: int | None, customer_id: int | None, page: int, limit: int):
        filters = [cls.scope_clause(scope)]
        filters.append(OutgoingEmail.status == "draft" if folder == "drafts" else OutgoingEmail.status != "draft")
        if status:
            filters.append(OutgoingEmail.status == status)
        if order_id:
            filters.append(OutgoingEmail.order_id == order_id)
        if customer_id:
            filters.append(OutgoingEmail.customer_id == customer_id)
        if q:
            pattern = f"%{q.strip()}%"
            filters.append(or_(OutgoingEmail.subject.ilike(pattern), OutgoingEmail.recipient_email.ilike(pattern), OutgoingEmail.body_text.ilike(pattern)))
        # Messages associated with a storefront remain visible only in that context.
        filters.append(or_(OutgoingEmail.order_id.is_(None), OutgoingEmail.order_id.in_(
            select(Order.id).where(Order.tenant_id == scope.tenant_id, Order.storefront_id == scope.storefront_id)
        )))
        filters.append(or_(OutgoingEmail.customer_id.is_(None), OutgoingEmail.customer_id.in_(
            select(Customer.id).where(Customer.tenant_id == scope.tenant_id)
        )))
        total = int((await session.execute(select(func.count()).select_from(OutgoingEmail).where(*filters))).scalar_one())
        rows = list((await session.execute(select(OutgoingEmail, func.substr(OutgoingEmail.body_text, 1, 300)).options(
            defer(OutgoingEmail.body_text), defer(OutgoingEmail.body_html)
        ).where(*filters).order_by(
            OutgoingEmail.created_at.desc(), OutgoingEmail.id.desc()
        ).offset((page - 1) * limit).limit(limit))).all())
        return rows, total
