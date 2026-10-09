"""Explicit tender context and reversible associations, never business-record merges."""
from sqlalchemy import or_
from sqlmodel import select

from models import Customer, LeadSource, Order, OrderStatus
from models.leads_inbox import InboxEvent, InboxTriageState
from models.tender_workflow import TenderWorkflowContext, TenderWorkflowLink
from schemas_leads_inbox import LeadsInboxHistoryResponse, TenderWorkflowIdentity, TenderWorkflowResponse
from services.command_transaction import command_transaction
from services.leads_inbox_command_service import LeadsInboxCommandService
from services.leads_inbox_service import InboxError, LeadsInboxService
from services.tenant_entity_access_service import TenantEntityAccessService


class TenderWorkflowService:
    @staticmethod
    def scope(model, scope):
        return (model.tenant_id == scope.tenant_id) & (model.storefront_id == scope.storefront_id)

    @classmethod
    async def order(cls, session, order_id, scope, *, lock=False):
        if lock and scope.demo_read_only:
            raise InboxError("Демонстрационный доступ: изменения запрещены", 403)
        order = await TenantEntityAccessService.get_order(session, order_id, tenant_scope=scope,
            for_update=lock, populate_existing=lock)
        if not order or order.lead_source not in (LeadSource.EMAIL, LeadSource.BELZAKUPKI):
            raise InboxError("Закупка не найдена", 404)
        if order.linked_order_id:
            raise InboxError("Письмо привязано к заказу: работайте с исходной закупкой")
        return order

    @classmethod
    async def context(cls, session, order_id, scope):
        return (await session.execute(select(TenderWorkflowContext).where(
            TenderWorkflowContext.order_id == order_id, cls.scope(TenderWorkflowContext, scope))
            .execution_options(populate_existing=True))).scalar_one_or_none()

    @staticmethod
    def effective_deadline(order, context):
        return context.deadline_at if context and context.deadline_manual else LeadsInboxService.deadline_value(order.technical_meta)

    @classmethod
    async def identity(cls, session, order, scope):
        context = await cls.context(session, order.id, scope)
        state = (await session.execute(select(InboxTriageState).where(InboxTriageState.entity_kind == "order",
            InboxTriageState.entity_id == order.id, cls.scope(InboxTriageState, scope)))).scalar_one_or_none()
        return cls.identity_value(order, context, state)

    @classmethod
    def identity_value(cls, order, context, state):
        meta = order.technical_meta if isinstance(order.technical_meta, dict) else {}
        provider = meta.get("belzakupki") or {}
        tender = provider.get("tender") if isinstance(provider, dict) else {}
        tender = tender if isinstance(tender, dict) else {}
        manual = meta.get("inbox_tender") or {}
        return TenderWorkflowIdentity(order_id=order.id, title=order.title or tender.get("title") or meta.get("email_subject"),
            external_id=str(tender["external_id"]) if tender.get("external_id") is not None else None,
            source=tender.get("source") or getattr(order.lead_source, "value", order.lead_source),
            source_url=tender.get("url") or (manual.get("source_url") if isinstance(manual, dict) else None),
            status=getattr(order.status, "value", order.status), archived=bool(state and state.archived_at) or (
                order.status == OrderStatus.CLOSED and order.closing_result == "lost"),
            stage=context.stage if context else None, deadline_at=cls.effective_deadline(order, context))

    @classmethod
    async def project_orders(cls, session, orders, tenant_scope):
        """Batch page context and related identities; keep queue reads independent of page size."""
        order_index = {order.id: order for order in orders}
        ids = list(order_index)
        if not ids:
            return {}
        links = (await session.execute(select(TenderWorkflowLink).where(cls.scope(TenderWorkflowLink, tenant_scope),
            or_(TenderWorkflowLink.publication_order_id.in_(ids), TenderWorkflowLink.price_order_id.in_(ids))))).scalars().all()
        related_ids = {value for link in links for value in (link.publication_order_id, link.price_order_id)} - set(ids)
        if related_ids:
            related = (await session.execute(select(Order).outerjoin(Customer, Customer.id == Order.customer_id).where(
                Order.id.in_(related_ids), TenantEntityAccessService.order_clause(tenant_scope),
                TenantEntityAccessService.order_customer_clause(tenant_scope)))).scalars().all()
            order_index.update({order.id: order for order in related})
        contexts = (await session.execute(select(TenderWorkflowContext).where(
            TenderWorkflowContext.order_id.in_(order_index), cls.scope(TenderWorkflowContext, tenant_scope)))).scalars().all()
        context_index = {context.order_id: context for context in contexts}
        states = (await session.execute(select(InboxTriageState).where(InboxTriageState.entity_kind == "order",
            InboxTriageState.entity_id.in_(order_index), cls.scope(InboxTriageState, tenant_scope)))).scalars().all()
        state_index = {state.entity_id: state for state in states}
        results = {}
        for order_id in ids:
            context = context_index.get(order_id)
            if not context:
                continue
            price, publications = None, []
            for link in links:
                related_id = link.price_order_id if link.publication_order_id == order_id else (
                    link.publication_order_id if link.price_order_id == order_id else None)
                if related_id not in order_index:
                    continue
                identity = cls.identity_value(order_index[related_id], context_index.get(related_id), state_index.get(related_id))
                if link.publication_order_id == order_id:
                    price = identity
                else:
                    publications.append(identity)
            results[order_id] = TenderWorkflowResponse(order_id=order_id, stage=context.stage,
                deadline_at=cls.effective_deadline(order_index[order_id], context), deadline_manual=context.deadline_manual,
                price_enquiry=price, publications=publications)
        return results

    @classmethod
    async def read(cls, session, *, order_id, tenant_scope, include_history=True):
        order = await cls.order(session, order_id, tenant_scope)
        context = await cls.context(session, order_id, tenant_scope)
        links = (await session.execute(select(TenderWorkflowLink).where(cls.scope(TenderWorkflowLink, tenant_scope),
            or_(TenderWorkflowLink.publication_order_id == order_id, TenderWorkflowLink.price_order_id == order_id)))).scalars().all()
        price, publications = None, []
        for link in links:
            related_id = link.price_order_id if link.publication_order_id == order_id else link.publication_order_id
            related = await cls.order(session, related_id, tenant_scope)
            identity = await cls.identity(session, related, tenant_scope)
            if link.publication_order_id == order_id:
                price = identity
            else:
                publications.append(identity)
        history = []
        if include_history:
            events = (await session.execute(select(InboxEvent).where(InboxEvent.entity_kind == "order",
                InboxEvent.entity_id == order_id, cls.scope(InboxEvent, tenant_scope),
                InboxEvent.kind.in_(["tender_stage", "tender_link", "tender_unlink"]))
                .order_by(InboxEvent.created_at.desc(), InboxEvent.id.desc()).limit(100))).scalars().all()
            history = [LeadsInboxHistoryResponse.model_validate(event) for event in events]
        return TenderWorkflowResponse(order_id=order_id, stage=context.stage if context else None,
            deadline_at=cls.effective_deadline(order, context), deadline_manual=bool(context and context.deadline_manual),
            price_enquiry=price, publications=publications, history=history)

    @classmethod
    async def update(cls, session, *, order_id, tenant_scope, username, payload):
        async with command_transaction(session):
            order = await cls.order(session, order_id, tenant_scope, lock=True)
            context = await cls.context(session, order_id, tenant_scope)
            links = (await session.execute(select(TenderWorkflowLink).where(cls.scope(TenderWorkflowLink, tenant_scope),
                or_(TenderWorkflowLink.publication_order_id == order_id, TenderWorkflowLink.price_order_id == order_id)))).scalars().all()
            is_price = payload.stage in ("price_request", "price_sent")
            if any((link.publication_order_id == order_id and is_price) or (
                    link.price_order_id == order_id and not is_price) for link in links):
                raise InboxError("Сначала снимите связь между запросом цены и публикацией")
            context = context or TenderWorkflowContext(order_id=order_id, tenant_id=order.tenant_id,
                storefront_id=order.storefront_id, stage=payload.stage)
            deadline = payload.deadline_at if "deadline_at" in payload.model_fields_set else (
                context.deadline_at if context.stage == payload.stage else None)
            if context.stage != payload.stage or not context.deadline_manual or context.deadline_at != deadline:
                before = f"{context.stage}; {context.deadline_at.isoformat() if context.deadline_at else 'без срока'}"
                context.stage, context.deadline_at, context.deadline_manual = payload.stage, deadline, True
                session.add(context)
                session.add(LeadsInboxCommandService.event(order, kind="tender_stage", actor=username,
                    note=f"{before} → {payload.stage}; {deadline.isoformat() if deadline else 'без срока'}"))
                await session.flush()
        return await cls.read(session, order_id=order_id, tenant_scope=tenant_scope)

    @classmethod
    async def associate(cls, session, *, order_id, price_order_id, tenant_scope, username):
        if order_id == price_order_id:
            raise InboxError("Запрос цены и публикация должны быть разными обращениями")
        async with command_transaction(session):
            # Both roots serialize with imports/expiry; ascending IDs prevent crossed-link deadlocks.
            roots = {root_id: await cls.order(session, root_id, tenant_scope, lock=True)
                for root_id in sorted([order_id, price_order_id])}
            publication, price = roots[order_id], roots[price_order_id]
            price_context = await cls.context(session, price_order_id, tenant_scope)
            if not price_context or price_context.stage not in ("price_request", "price_sent"):
                raise InboxError("У исходного обращения выберите этап запроса цены или отправленного предложения")
            links = (await session.execute(select(TenderWorkflowLink).where(cls.scope(TenderWorkflowLink, tenant_scope),
                or_(TenderWorkflowLink.publication_order_id.in_([order_id, price_order_id]),
                    TenderWorkflowLink.price_order_id == order_id)))).scalars().all()
            if any(link.publication_order_id == price_order_id or link.price_order_id == order_id for link in links):
                raise InboxError("Связь не может образовывать цепочку или цикл")
            existing = next((link for link in links if link.publication_order_id == order_id), None)
            if existing and existing.price_order_id != price_order_id:
                raise InboxError("Сначала снимите текущую связь с запросом цены")
            if not existing:
                context = await cls.context(session, order_id, tenant_scope)
                if context and context.stage in ("price_request", "price_sent"):
                    raise InboxError("Для публикации выберите этап «Объявлена / готовим заявку»")
                if not context:
                    session.add(TenderWorkflowContext(order_id=order_id, tenant_id=publication.tenant_id,
                        storefront_id=publication.storefront_id, stage="announced"))
                session.add(TenderWorkflowLink(publication_order_id=order_id, price_order_id=price_order_id,
                    tenant_id=publication.tenant_id, storefront_id=publication.storefront_id))
                for order in (publication, price):
                    session.add(LeadsInboxCommandService.event(order, kind="tender_link", actor=username,
                        note=f"Публикация #{order_id} связана с запросом цены #{price_order_id}"))
                await session.flush()
        return await cls.read(session, order_id=order_id, tenant_scope=tenant_scope)

    @classmethod
    async def dissociate(cls, session, *, order_id, tenant_scope, username):
        if tenant_scope.demo_read_only:
            raise InboxError("Демонстрационный доступ: изменения запрещены", 403)
        # Resolve IDs, then lock both roots in the same order as association.
        link = (await session.execute(select(TenderWorkflowLink).where(
            TenderWorkflowLink.publication_order_id == order_id, cls.scope(TenderWorkflowLink, tenant_scope)))).scalar_one_or_none()
        await cls.order(session, order_id, tenant_scope)
        if not link:
            return await cls.read(session, order_id=order_id, tenant_scope=tenant_scope)
        price_id = link.price_order_id
        async with command_transaction(session):
            roots = {root_id: await cls.order(session, root_id, tenant_scope, lock=True)
                for root_id in sorted([order_id, price_id])}
            link = (await session.execute(select(TenderWorkflowLink).where(
                TenderWorkflowLink.publication_order_id == order_id, cls.scope(TenderWorkflowLink, tenant_scope))
                .execution_options(populate_existing=True))).scalar_one_or_none()
            if link is not None and link.price_order_id != price_id:
                raise InboxError("Связь изменилась: обновите закупку")
            if link is not None:
                await session.delete(link)
                for order in roots.values():
                    session.add(LeadsInboxCommandService.event(order, kind="tender_unlink", actor=username,
                        note=f"Снята связь публикации #{order_id} с запросом цены #{price_id}"))
                await session.flush()
        return await cls.read(session, order_id=order_id, tenant_scope=tenant_scope)

    @classmethod
    async def candidates(cls, session, *, order_id, tenant_scope, search=None, limit=20):
        await cls.order(session, order_id, tenant_scope)
        query = (select(Order).outerjoin(TenderWorkflowContext, TenderWorkflowContext.order_id == Order.id)
            .outerjoin(Customer, Customer.id == Order.customer_id)
            .where(TenantEntityAccessService.order_clause(tenant_scope),
                TenantEntityAccessService.order_customer_clause(tenant_scope),
                or_(TenderWorkflowContext.order_id.is_(None),
                    cls.scope(TenderWorkflowContext, tenant_scope) & TenderWorkflowContext.stage.in_(["price_request", "price_sent"])),
                Order.lead_source.in_([LeadSource.EMAIL, LeadSource.BELZAKUPKI]),
                Order.id != order_id, Order.linked_order_id.is_(None)))
        if search and search.strip():
            query = query.where(LeadsInboxService.search_clause(search))
        orders = (await session.execute(query.order_by(Order.created_at.desc(), Order.id.desc()).limit(min(100, limit)))).scalars().all()
        return [await cls.identity(session, order, tenant_scope) for order in orders]
