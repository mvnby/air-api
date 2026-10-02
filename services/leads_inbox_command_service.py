"""Locked incoming decisions. A refusal archives only its incoming record."""

from datetime import timezone

from sqlmodel import select

from models import LeadSource, OrderStatus
from models.leads_inbox import InboxEvent, InboxReadState, InboxTriageState, utc_now
from services.command_transaction import command_transaction
from services.leads_inbox_service import InboxError, LeadsInboxService
from services.tenant_entity_access_service import TenantEntityAccessService


class LeadsInboxCommandService:
    @staticmethod
    async def locked(session, *, order_id, tenant_scope):
        if tenant_scope.demo_read_only:
            raise InboxError("Демонстрационный доступ: изменения запрещены", 403)
        order = await TenantEntityAccessService.get_order(session, order_id, tenant_scope=tenant_scope,
            for_update=True, populate_existing=True)
        if not order:
            raise InboxError("Входящее обращение не найдено", 404)
        state = (await session.execute(select(InboxTriageState).where(
            InboxTriageState.entity_kind == "order", InboxTriageState.entity_id == order_id,
            InboxTriageState.tenant_id == tenant_scope.tenant_id)
            .execution_options(populate_existing=True))).scalar_one_or_none()
        is_legacy_archive = order.status == OrderStatus.CLOSED and order.closing_result == "lost"
        if order.status != OrderStatus.NEW_LEAD and not is_legacy_archive and not (state and state.archived_at):
            raise InboxError("Обращение уже принято в работу")
        return order, state

    @staticmethod
    def active(order, state):
        if order.status != OrderStatus.NEW_LEAD or order.linked_order_id or (state and state.archived_at):
            raise InboxError("Обращение уже обработано или находится в архиве")

    @staticmethod
    def state(order):
        return InboxTriageState(entity_kind="order", entity_id=order.id, order_id=order.id,
            tenant_id=order.tenant_id, storefront_id=order.storefront_id)

    @staticmethod
    def event(order, *, kind, actor, **fields):
        return InboxEvent(entity_kind="order", entity_id=order.id, order_id=order.id,
            tenant_id=order.tenant_id, storefront_id=order.storefront_id, kind=kind, actor=actor, **fields)

    @classmethod
    async def read(cls, session, *, order_id, username, tenant_scope, is_read):
        async with command_transaction(session):
            order, _ = await cls.locked(session, order_id=order_id, tenant_scope=tenant_scope)
            state = (await session.execute(select(InboxReadState).where(InboxReadState.tenant_id == tenant_scope.tenant_id,
                InboxReadState.username == username, InboxReadState.entity_kind == "order",
                InboxReadState.entity_id == order_id).execution_options(populate_existing=True))).scalar_one_or_none()
            if not state:
                state = InboxReadState(tenant_id=order.tenant_id, storefront_id=order.storefront_id,
                    username=username, entity_kind="order", entity_id=order_id, order_id=order_id)
            state.is_read = is_read
            state.read_at = (state.read_at or utc_now()) if is_read else None
            session.add(state)
            await session.flush()
        return await LeadsInboxService.detail(session, order_id=order_id, username=username, tenant_scope=tenant_scope)

    @classmethod
    async def archive(cls, session, *, order_id, username, tenant_scope, payload):
        async with command_transaction(session):
            order, state = await cls.locked(session, order_id=order_id, tenant_scope=tenant_scope)
            cls.active(order, state)
            state = state or cls.state(order)
            state.outcome, state.reason, state.note = payload.outcome, payload.reason, payload.note
            state.archived_at, state.archived_by = utc_now(), username
            session.add(state)
            session.add(cls.event(order, kind="archive", actor=username,
                outcome=payload.outcome, reason=payload.reason, note=payload.note))
            await session.flush()
        return await LeadsInboxService.detail(session, order_id=order_id, username=username, tenant_scope=tenant_scope)

    @classmethod
    async def restore(cls, session, *, order_id, username, tenant_scope):
        async with command_transaction(session):
            order, state = await cls.locked(session, order_id=order_id, tenant_scope=tenant_scope)
            if order.linked_order_id:
                raise InboxError("Сначала отмените связь с заказом")
            legacy = order.status == OrderStatus.CLOSED and order.closing_result == "lost"
            if not legacy and not (state and state.archived_at):
                raise InboxError("Обращение уже активно")
            previous_note = state.note if state and state.archived_at else order.reject_reason
            previous_reason = state.reason if state and state.archived_at else None
            if legacy:
                order.status, order.closing_result, order.reject_reason = OrderStatus.NEW_LEAD, None, None
                session.add(order)
            state = state or cls.state(order)
            previous_outcome = state.outcome or "legacy_lost"
            # Suppress the current deadline even when a manual refusal is restored.
            state.restored_deadline_at = LeadsInboxService.deadline_value(order.technical_meta)
            state.archived_at = state.archived_by = state.outcome = state.reason = state.note = None
            session.add(state)
            session.add(cls.event(order, kind="restore", actor=username, outcome=previous_outcome,
                reason=previous_reason, note=previous_note))
            await session.flush()
        return await LeadsInboxService.detail(session, order_id=order_id, username=username, tenant_scope=tenant_scope)

    @classmethod
    async def no_answer(cls, session, *, order_id, username, tenant_scope, payload):
        async with command_transaction(session):
            order, state = await cls.locked(session, order_id=order_id, tenant_scope=tenant_scope)
            cls.active(order, state)
            if "next_followup_at" in payload.model_fields_set:
                order.next_followup_date = (payload.next_followup_at.astimezone(timezone.utc).replace(tzinfo=None)
                                           if payload.next_followup_at else None)
            session.add(order)
            session.add(cls.event(order, kind="no_answer", actor=username, note=payload.note,
                next_followup_at=payload.next_followup_at))
            await session.flush()
        return await LeadsInboxService.detail(session, order_id=order_id, username=username, tenant_scope=tenant_scope)

    @classmethod
    async def tender_context(cls, session, *, order_id, username, tenant_scope, payload):
        async with command_transaction(session):
            order, state = await cls.locked(session, order_id=order_id, tenant_scope=tenant_scope)
            cls.active(order, state)
            if order.lead_source != LeadSource.EMAIL:
                raise InboxError("Подтверждение вида обращения доступно для писем")
            meta = dict(order.technical_meta) if isinstance(order.technical_meta, dict) else {}
            previous = meta.get("inbox_tender")
            previous = previous if isinstance(previous, dict) else {}
            deadline = (payload.deadline_at.astimezone(timezone.utc).isoformat() if payload.deadline_at else None
                        ) if "deadline_at" in payload.model_fields_set else previous.get("deadline_at")
            source_url = payload.source_url if "source_url" in payload.model_fields_set else previous.get("source_url")
            now = utc_now()
            meta["inbox_tender"] = {"confirmed": True, "is_tender": payload.is_tender,
                "deadline_at": deadline if payload.is_tender else None,
                "source_url": source_url if payload.is_tender else None,
                "confirmed_by": username, "confirmed_at": now.isoformat()}
            order.technical_meta = meta
            session.add(order)
            session.add(cls.event(order, kind="tender_context", actor=username,
                note=(f"Менеджер подтвердил закупку. Срок подачи: {deadline or 'не указан'}. "
                      f"Источник: {source_url or 'не указан'}") if payload.is_tender else "Менеджер указал обычное обращение"))
            await session.flush()
        return await LeadsInboxService.detail(session, order_id=order_id, username=username, tenant_scope=tenant_scope)
