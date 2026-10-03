"""A single paginated feed over Order intakes and unqualified Lead intakes."""
from datetime import datetime, timezone

from sqlalchemy import String, case, cast, func, literal, or_, union_all
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import Lead, LeadSource, Order
from models.leads_inbox import InboxEvent
from schemas_common import Meta
from schemas_leads_inbox import LeadsCounterResponse, LeadsInboxListResponse
from services.leads_inbox_service import LeadsInboxService
from services.raw_lead_inbox_service import RawLeadInboxService


class UnifiedInboxService:
    @staticmethod
    def source_column(column):
        # Historical empty or unknown sources still belong to the visible Other filter.
        return case((column.in_([source.value for source in LeadSource]), column), else_='other')

    @staticmethod
    def raw_search(search):
        text = search.strip().replace('!', '!!').replace('%', '!%').replace('_', '!_')
        pattern = f'%{text}%'
        return or_(*(field.ilike(pattern, escape='!') for field in (
            Lead.name, Lead.company_name, Lead.phone, Lead.email, Lead.inn,
            Lead.request_text, cast(Lead.id, String))))

    @classmethod
    async def counts(cls, session, *, username, tenant_scope):
        result = await LeadsInboxService.counts(session, username=username, tenant_scope=tenant_scope)
        root = RawLeadInboxService.base_statement(username, tenant_scope).where(RawLeadInboxService.scope_clause('active'))
        pending = int((await session.execute(select(func.count()).select_from(root.subquery()))).scalar() or 0)
        unread = int((await session.execute(select(func.count()).select_from(
            root.where(LeadsInboxService.unread_clause()).subquery()))).scalar() or 0)
        total_unread = result.unread_count + unread
        return LeadsCounterResponse(count=total_unread, has_new=bool(total_unread),
            unread_count=total_unread, pending_count=result.pending_count + pending)

    @classmethod
    async def get_leads_inbox(cls, session, *, tenant_scope, username='', scope='active', page=1,
                              limit=50, search=None, source=None, unread_only=False, sort='newest'):
        page, limit = max(1, int(page or 1)), min(100, max(1, int(limit or 50)))
        orders = LeadsInboxService.base_statement(username=username, tenant_scope=tenant_scope).where(LeadsInboxService.scope_clause(scope))
        leads = RawLeadInboxService.base_statement(username, tenant_scope).where(RawLeadInboxService.scope_clause(scope))
        if search and search.strip():
            orders, leads = orders.where(LeadsInboxService.search_clause(search)), leads.where(cls.raw_search(search))
        if unread_only:
            orders, leads = orders.where(LeadsInboxService.unread_clause()), leads.where(LeadsInboxService.unread_clause())
        order_source, lead_source = cls.source_column(Order.lead_source), cls.source_column(Lead.source)
        sources = union_all(orders.with_only_columns(order_source.label('source')),
                            leads.with_only_columns(lead_source.label('source'))).subquery()
        source_counts = dict((await session.execute(select(sources.c.source, func.count())
            .group_by(sources.c.source))).all())
        if source is not None:
            source_value = source.value if hasattr(source, 'value') else source
            orders, leads = orders.where(order_source == source_value), leads.where(lead_source == source_value)
        order_columns = [literal('order').label('kind'), Order.id.label('entity_id'), Order.created_at.label('created_at')]
        lead_columns = [literal('lead').label('kind'), Lead.id.label('entity_id'), Lead.created_at.label('created_at')]
        if sort == 'deadline':
            deadline_columns = LeadsInboxService.deadline_columns()
            order_columns.extend(deadline_columns)
            lead_columns.extend(literal(None, type_=column.type).label(column.name) for column in deadline_columns)
        roots = union_all(orders.with_only_columns(*order_columns), leads.with_only_columns(*lead_columns)).subquery()
        total = int((await session.execute(select(func.count()).select_from(roots))).scalar() or 0)
        if sort == 'deadline':
            narrow_rows = (await session.execute(select(roots))).all()
            far = datetime.max.replace(tzinfo=timezone.utc)
            def key(row):
                created = row.created_at.replace(tzinfo=timezone.utc) if row.created_at.tzinfo is None else row.created_at
                return LeadsInboxService.root_deadline(row) or far, -created.timestamp(), row.kind, -row.entity_id
            selected = sorted(narrow_rows, key=key)[(page - 1) * limit:page * limit]
        else:
            selected = (await session.execute(select(roots).order_by(roots.c.created_at.desc(), roots.c.kind, roots.c.entity_id.desc())
                .offset((page - 1) * limit).limit(limit))).all()
        order_ids = [row.entity_id for row in selected if row.kind == 'order']
        lead_ids = [row.entity_id for row in selected if row.kind == 'lead']
        items = []
        if order_ids:
            order_rows = (await session.execute(orders.where(Order.id.in_(order_ids)).options(selectinload(Order.customer)))).all()
            projected = await LeadsInboxService.project_rows(session, order_rows, tenant_scope=tenant_scope)
            from services.inbox_source_relations import add_source_relations
            await add_source_relations(session, rows=order_rows, items=projected, tenant_scope=tenant_scope)
            items.extend(projected)
        if lead_ids:
            lead_rows = (await session.execute(leads.where(Lead.id.in_(lead_ids)))).all()
            raw_items = [RawLeadInboxService.project(*row) for row in lead_rows]
            attempts = (await session.execute(select(InboxEvent.entity_id, func.count(InboxEvent.id), func.max(InboxEvent.created_at))
                .where(InboxEvent.entity_kind == 'lead', InboxEvent.entity_id.in_(lead_ids),
                    InboxEvent.tenant_id == tenant_scope.tenant_id, InboxEvent.kind == 'no_answer')
                .where(InboxEvent.storefront_id == tenant_scope.storefront_id)
                .group_by(InboxEvent.entity_id))).all()
            by_lead = {row[0]: (row[1], row[2]) for row in attempts}
            for item in raw_items:
                item.no_answer_count, item.no_answer_at = by_lead.get(item.id, (0, None))
            items.extend(raw_items)
        index = {(item.entity_kind, item.id): item for item in items}
        items = [index[(row.kind, row.entity_id)] for row in selected if (row.kind, row.entity_id) in index]
        counts = await cls.counts(session, username=username, tenant_scope=tenant_scope)
        return LeadsInboxListResponse(items=items, total=total,
            meta=Meta(total=total, page=page, limit=limit, pages=(total + limit - 1) // limit),
            pending_count=counts.pending_count, unread_count=counts.unread_count, source_counts=source_counts)
