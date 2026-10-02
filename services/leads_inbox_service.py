"""Tenant-scoped incoming Order reads and personal unread counters."""

from datetime import datetime, timezone

from sqlalchemy import String, and_, cast, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Customer, GlobalConfig, LeadSource, Order, OrderStatus
from models.leads_inbox import InboxEvent, InboxReadState, InboxTriageState
from models.tenancy import TenantScope
from schemas_common import Meta
from schemas_leads_inbox import LeadsCounterResponse, LeadsInboxDetailResponse, LeadsInboxHistoryResponse, LeadsInboxListResponse
from services.leads_inbox_projection import LeadsInboxProjection
from services.tenant_entity_access_service import TenantEntityAccessService


class InboxError(ValueError):
    def __init__(self, message: str, status_code: int = 409):
        super().__init__(message)
        self.status_code = status_code


class LeadsInboxService:
    @staticmethod
    def unread_clause():
        return or_(InboxReadState.is_read.is_(None), InboxReadState.is_read.is_(False))

    @staticmethod
    def scope_clause(scope):
        active = and_(Order.status == OrderStatus.NEW_LEAD, Order.linked_order_id.is_(None),
                      InboxTriageState.archived_at.is_(None))
        archive = or_(InboxTriageState.archived_at.is_not(None),
                      and_(Order.status == OrderStatus.CLOSED, Order.closing_result == "lost"),
                      and_(Order.status == OrderStatus.NEW_LEAD, Order.linked_order_id.is_not(None)))
        return archive if scope == "archive" else active

    @staticmethod
    def base_statement(*, username: str, tenant_scope: TenantScope):
        return (select(Order, InboxTriageState, InboxReadState)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .outerjoin(InboxTriageState, and_(InboxTriageState.entity_kind == "order",
                InboxTriageState.entity_id == Order.id, InboxTriageState.tenant_id == Order.tenant_id))
            .outerjoin(InboxReadState, and_(InboxReadState.entity_kind == "order",
                InboxReadState.entity_id == Order.id, InboxReadState.tenant_id == Order.tenant_id,
                InboxReadState.username == username))
            .where(TenantEntityAccessService.order_clause(tenant_scope),
                   TenantEntityAccessService.order_customer_clause(tenant_scope)))

    @staticmethod
    def search_clause(search):
        term = search.strip().replace("!", "!!").replace("%", "!%").replace("_", "!_")
        pattern = f"%{term}%"
        return or_(Order.title.ilike(pattern, escape="!"), Order.comment.ilike(pattern, escape="!"),
            cast(Order.id, String).ilike(pattern, escape="!"), Customer.name.ilike(pattern, escape="!"),
            Customer.full_legal_name.ilike(pattern, escape="!"), Customer.phone.ilike(pattern, escape="!"),
            Customer.email.ilike(pattern, escape="!"), Customer.inn.ilike(pattern, escape="!"),
            and_(Order.lead_source == LeadSource.BELZAKUPKI,
                Order.technical_meta["belzakupki"]["tender"]["customer_name"].as_string().ilike(pattern, escape="!")))

    @classmethod
    async def counts(cls, session, *, username, tenant_scope):
        root = cls.base_statement(username=username, tenant_scope=tenant_scope).where(cls.scope_clause("active"))
        pending = int((await session.execute(select(func.count()).select_from(root.subquery()))).scalar() or 0)
        unread = int((await session.execute(select(func.count()).select_from(
            root.where(cls.unread_clause()).subquery()))).scalar() or 0)
        return LeadsCounterResponse(count=unread, has_new=unread > 0, pending_count=pending, unread_count=unread)

    @staticmethod
    def deadline_fields(deadline_at=None, deadline_kind=None, manual_deadline_at=None,
                        manual_confirmed=None, manual_is_tender=None):
        if manual_confirmed is True and manual_is_tender is True:
            raw = manual_deadline_at
        else:
            if deadline_kind not in (None, "submission"):
                return None
            raw = deadline_at
        try:
            value = datetime.fromisoformat(str(raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
        if value.tzinfo is None or value.utcoffset() is None:
            return None
        return value.astimezone(timezone.utc)

    @classmethod
    def deadline_value(cls, meta):
        """Only structured submission deadlines are trusted; never infer from prose."""
        if not isinstance(meta, dict):
            return None
        provider, confirmed = meta.get("belzakupki"), meta.get("inbox_tender")
        tender = provider.get("tender") if isinstance(provider, dict) else None
        tender = tender if isinstance(tender, dict) else {}
        confirmed = confirmed if isinstance(confirmed, dict) else {}
        return cls.deadline_fields(tender.get("deadline_at"), tender.get("deadline_kind"),
            confirmed.get("deadline_at"), confirmed.get("confirmed"), confirmed.get("is_tender"))

    @staticmethod
    def deadline_columns():
        tender, manual = Order.technical_meta["belzakupki"]["tender"], Order.technical_meta["inbox_tender"]
        return [tender["deadline_at"].as_string().label("deadline_at"),
            tender["deadline_kind"].as_string().label("deadline_kind"),
            manual["deadline_at"].as_string().label("manual_deadline_at"),
            manual["confirmed"].as_json().label("manual_confirmed"),
            manual["is_tender"].as_json().label("manual_is_tender")]

    @classmethod
    def root_deadline(cls, row):
        return cls.deadline_fields(row.deadline_at, row.deadline_kind, row.manual_deadline_at,
            row.manual_confirmed, row.manual_is_tender)

    @classmethod
    async def get_leads_inbox(cls, session: AsyncSession, *, tenant_scope: TenantScope,
            username: str = "", scope="active", page=1, limit=50, search=None, source=None,
            unread_only=False, sort="newest"):
        page = max(1, int(page or 1))
        limit = min(100, max(1, int(limit or 50)))
        stmt = cls.base_statement(username=username, tenant_scope=tenant_scope).where(cls.scope_clause(scope))
        if source is not None:
            stmt = stmt.where(Order.lead_source == source)
        if search and search.strip():
            stmt = stmt.where(cls.search_clause(search))
        if unread_only:
            stmt = stmt.where(cls.unread_clause())
        total = int((await session.execute(select(func.count()).select_from(stmt.subquery()))).scalar() or 0)
        if sort == "deadline":
            # Parse narrow metadata roots before pagination. Historical malformed
            # JSON must never make a PostgreSQL datetime cast break the queue.
            roots = (await session.execute(stmt.with_only_columns(Order.id, Order.created_at, *cls.deadline_columns()))).all()
            far = datetime.max.replace(tzinfo=timezone.utc)
            ordered = sorted(roots, key=lambda row: (cls.root_deadline(row) or far,
                              -row.created_at.replace(tzinfo=timezone.utc).timestamp(), -row.id))
            ids = [row.id for row in ordered[(page - 1) * limit:page * limit]]
            rows = (await session.execute(stmt.where(Order.id.in_(ids)).options(selectinload(Order.customer)))).all()
            index = {item[0].id: item for item in rows}
            rows = [index[entity_id] for entity_id in ids if entity_id in index]
        else:
            rows = (await session.execute(stmt.options(selectinload(Order.customer))
                    .order_by(Order.created_at.desc(), Order.id.desc()).offset((page - 1) * limit).limit(limit))).all()
        items = await cls.project_rows(session, rows, tenant_scope=tenant_scope)
        counts = await cls.counts(session, username=username, tenant_scope=tenant_scope)
        return LeadsInboxListResponse(items=items, total=total,
            meta=Meta(total=total, page=page, limit=limit, pages=(total + limit - 1) // limit),
            pending_count=counts.pending_count, unread_count=counts.unread_count)

    @classmethod
    async def project_rows(cls, session, rows, *, tenant_scope):
        from services.service_attachment_service import ServiceAttachmentService

        ids = [int(row[0].id) for row in rows]
        mode = (await session.execute(select(GlobalConfig.value).where(
            GlobalConfig.key == "inbox_tender_archive_mode"))).scalar_one_or_none()
        attachments = await ServiceAttachmentService.order_attachment_counts(session, order_ids=ids, tenant_scope=tenant_scope)
        events = (await session.execute(select(InboxEvent.entity_id, func.count(InboxEvent.id), func.max(InboxEvent.created_at))
            .where(InboxEvent.entity_kind == "order", InboxEvent.entity_id.in_(ids),
                InboxEvent.tenant_id == tenant_scope.tenant_id, InboxEvent.storefront_id == tenant_scope.storefront_id,
                InboxEvent.kind == "no_answer").group_by(InboxEvent.entity_id))).all()
        followups = {row[0]: (row[1], row[2]) for row in events}
        return [LeadsInboxProjection.item(order, state=state, read=read,
            attachment_count=attachments.get(order.id, 0),
            auto_archive_enabled=mode == "execute",
            no_answer_count=followups.get(order.id, (0, None))[0],
            no_answer_at=followups.get(order.id, (0, None))[1]) for order, state, read in rows]

    @classmethod
    async def detail(cls, session, *, order_id, username, tenant_scope):
        stmt = cls.base_statement(username=username, tenant_scope=tenant_scope).where(Order.id == order_id)
        # The incoming endpoint never exposes arbitrary qualified orders.
        stmt = stmt.where(or_(cls.scope_clause("active"), cls.scope_clause("archive")))
        row = (await session.execute(stmt.options(selectinload(Order.customer)))).first()
        if not row:
            raise InboxError("Входящее обращение не найдено", 404)
        item = (await cls.project_rows(session, [row], tenant_scope=tenant_scope))[0]
        events = (await session.execute(select(InboxEvent).where(InboxEvent.entity_kind == "order",
            InboxEvent.entity_id == order_id, InboxEvent.tenant_id == tenant_scope.tenant_id,
            InboxEvent.storefront_id == tenant_scope.storefront_id)
            .order_by(InboxEvent.created_at.desc(), InboxEvent.id.desc()).limit(100))).scalars().all()
        meta = row[0].technical_meta if isinstance(row[0].technical_meta, dict) else {}
        return LeadsInboxDetailResponse(**item.model_dump(), original_text=meta.get("email_source_text"),
            original_text_truncated=bool(meta.get("email_source_text_truncated")), history=[LeadsInboxHistoryResponse.model_validate(e) for e in events])
