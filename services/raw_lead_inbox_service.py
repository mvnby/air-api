"""Triage projection for unqualified contact leads without premature customers."""
from datetime import datetime, timezone

from sqlalchemy import and_, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Lead, LeadStatus
from models.leads_inbox import InboxEvent, InboxReadState, InboxTriageState
from models.tenancy import TenantScope
from schemas_leads_inbox import (
    InboxArchivePayload, InboxNoAnswerPayload, LeadsInboxArchiveResponse,
    LeadsInboxDetailResponse, LeadsInboxHistoryResponse, LeadsInboxItemResponse,
)
from services.command_transaction import command_transaction
from services.tenant_entity_access_service import TenantEntityAccessService


def now_utc():
    return datetime.now(timezone.utc)


class RawLeadInboxService:
    @staticmethod
    def base_statement(username: str, tenant_scope: TenantScope):
        return (select(Lead, InboxReadState, InboxTriageState)
            .outerjoin(InboxReadState, and_(InboxReadState.entity_kind == 'lead',
                InboxReadState.entity_id == Lead.id, InboxReadState.tenant_id == tenant_scope.tenant_id,
                InboxReadState.username == username))
            .outerjoin(InboxTriageState, and_(InboxTriageState.entity_kind == 'lead', InboxTriageState.entity_id == Lead.id,
                InboxTriageState.tenant_id == Lead.tenant_id, InboxTriageState.storefront_id == Lead.storefront_id))
            .where(TenantEntityAccessService.lead_clause(tenant_scope), Lead.converted_order_id.is_(None),
                   Lead.status != LeadStatus.qualified))

    @staticmethod
    def scope_clause(scope: str):
        if scope == 'active':
            return and_(Lead.status.in_([LeadStatus.new, LeadStatus.contacted]),
                        Lead.archived_at.is_(None), InboxTriageState.archived_at.is_(None))
        return or_(Lead.status.in_([LeadStatus.lost, LeadStatus.spam]),
                   Lead.archived_at.is_not(None), InboxTriageState.archived_at.is_not(None))

    @staticmethod
    def identity(lead: Lead):
        return dict(entity_kind='lead', entity_id=lead.id, lead_id=lead.id,
                    tenant_id=lead.tenant_id, storefront_id=lead.storefront_id)

    @staticmethod
    def project(lead: Lead, read: InboxReadState | None, state: InboxTriageState | None) -> LeadsInboxItemResponse:
        archive = None
        if state and state.archived_at:
            archive = LeadsInboxArchiveResponse(outcome=state.outcome, reason=state.reason, note=state.note,
                archived_at=state.archived_at, actor=state.archived_by)
        elif lead.status in (LeadStatus.lost, LeadStatus.spam) or lead.archived_at:
            archive = LeadsInboxArchiveResponse(outcome='spam' if lead.status == LeadStatus.spam else 'legacy_lost',
                reason=lead.loss_reason, archived_at=lead.archived_at)
        is_read = bool(read and read.is_read)
        lines = [line.strip() for line in lead.request_text.splitlines() if line.strip()]
        subject = next((line for line in lines if line != 'Заявка с сайта' and not line.startswith('Адрес/район:')), None)
        location = next((line.partition(':')[2].strip() for line in lines if line.startswith('Адрес/район:')), None)
        meta = lead.intake_meta or {}
        location = meta.get('address_text') or meta.get('region_text') or location
        missing = ([] if lead.phone or lead.email else ['contact']) + ([] if meta.get('address_text') else ['address'])
        intake_state = ('needs_contact' if 'contact' in missing else 'needs_details' if missing else 'ready_for_review') if lead.intake_event_key else None
        return LeadsInboxItemResponse(id=lead.id, entity_kind='lead', status=str(lead.status.value if hasattr(lead.status, 'value') else lead.status),
            is_new=not is_read and archive is None, is_read=is_read, read_at=read.read_at if read else None,
            title=(subject or 'Обращение с сайта')[:180], summary=lead.request_text[:400], comment=lead.request_text,
            customer_name=lead.company_name or lead.name, phone=lead.phone, email=lead.email, customer_inn=lead.inn,
            customer_full_legal_name=lead.company_name, location=location,
            customer_delivery_address=meta.get('address_text') if lead.intake_event_key else location,
            source=lead.source, created_at=lead.created_at, source_created_at=meta.get('source_occurred_at') or lead.created_at,
            workflow_type=meta.get('workflow_type'), service_type=meta.get('service_type'),
            intake_state=intake_state, intake_version=lead.version if intake_state else None,
            requested_time_text=meta.get('requested_time_text'), requested_at=meta.get('requested_at'),
            date_precision=meta.get('date_precision'), call_before_visit=meta.get('call_before_visit'),
            clarification_task_id=meta.get('clarification_task_id'),
            missing_fields=missing if intake_state else [],
            next_followup_at=(lead.next_followup_date.replace(tzinfo=timezone.utc)
                if lead.next_followup_date and lead.next_followup_date.tzinfo is None else lead.next_followup_date),
            archive=archive)

    @classmethod
    async def detail(cls, session: AsyncSession, lead_id: int, *, username: str, tenant_scope: TenantScope):
        row = (await session.execute(cls.base_statement(username, tenant_scope).where(Lead.id == lead_id))).first()
        if row is None:
            raise LookupError('Обращение не найдено')
        events = list((await session.execute(select(InboxEvent).where(
            InboxEvent.entity_kind == 'lead', InboxEvent.entity_id == lead_id,
            InboxEvent.tenant_id == tenant_scope.tenant_id,
            InboxEvent.storefront_id == tenant_scope.storefront_id,
        ).order_by(InboxEvent.created_at.desc(), InboxEvent.id.desc()).limit(100))).scalars())
        item = cls.project(*row)
        count, last_attempt = (await session.execute(select(func.count(InboxEvent.id), func.max(InboxEvent.created_at))
            .where(InboxEvent.entity_kind == 'lead', InboxEvent.entity_id == lead_id,
                InboxEvent.tenant_id == tenant_scope.tenant_id, InboxEvent.storefront_id == tenant_scope.storefront_id,
                InboxEvent.kind == 'no_answer'))).one()
        item.no_answer_count, item.no_answer_at = count, last_attempt
        return LeadsInboxDetailResponse(**item.model_dump(), original_text=(row[0].intake_meta or {}).get('original_text', row[0].request_text),
            history=[LeadsInboxHistoryResponse.model_validate(event) for event in events])

    @classmethod
    async def mutate(cls, session: AsyncSession, lead_id: int, *, username: str, tenant_scope: TenantScope,
                     action: str, payload=None):
        if tenant_scope.demo_read_only:
            raise PermissionError('Демонстрационный доступ: изменения запрещены')
        async with command_transaction(session):
            lead = await TenantEntityAccessService.get_lead(session, lead_id, tenant_scope=tenant_scope, for_update=True)
            if lead is None or lead.converted_order_id is not None or lead.status == LeadStatus.qualified:
                raise LookupError('Обращение не найдено')
            await session.refresh(lead)
            identity = cls.identity(lead)
            state = await session.get(InboxTriageState, ('lead', lead_id), populate_existing=True)
            archived = bool((state and state.archived_at) or lead.archived_at or lead.status in (LeadStatus.lost, LeadStatus.spam))
            if action == 'read':
                read = await session.get(InboxReadState, (tenant_scope.tenant_id, username, 'lead', lead_id), populate_existing=True)
                if read is None:
                    read = InboxReadState(**identity, username=username)
                read.is_read = payload.is_read
                read.read_at = now_utc() if payload.is_read else None
                session.add(read)
            elif action == 'archive':
                if archived:
                    raise ValueError('Обращение уже в архиве')
                if state is None:
                    state = InboxTriageState(**identity)
                state.outcome, state.reason, state.note = payload.outcome, payload.reason, payload.note
                state.archived_at, state.archived_by = now_utc(), username
                session.add(state)
                session.add(InboxEvent(**identity, kind='archive', actor=username, outcome=payload.outcome,
                    reason=payload.reason, note=payload.note))
            elif action == 'restore':
                if not archived:
                    raise ValueError('Обращение уже активно')
                old_reason = getattr(lead.loss_reason, 'value', lead.loss_reason)
                previous_outcome = (state.outcome if state and state.archived_at else
                    'spam' if lead.status == LeadStatus.spam else 'legacy_lost')
                previous_reason = state.reason if state and state.archived_at else old_reason
                legacy_notes = ([f'Прежняя причина: {old_reason}'] if old_reason else [])
                if lead.archived_at:
                    legacy_notes.append(f'Прежняя дата архива: {lead.archived_at.isoformat()}')
                previous_note = state.note if state and state.archived_at else '; '.join(legacy_notes) or None
                if state:
                    state.archived_at = None
                    state.archived_by = state.outcome = state.reason = state.note = None
                    session.add(state)
                lead.status, lead.archived_at, lead.loss_reason = LeadStatus.new, None, None
                session.add(lead)
                session.add(InboxEvent(**identity, kind='restore', actor=username,
                    outcome=previous_outcome, reason=previous_reason, note=previous_note))
            elif action == 'no-answer':
                if archived:
                    raise ValueError('Сначала восстановите обращение из архива')
                when = payload.next_followup_at
                if 'next_followup_at' in payload.model_fields_set:
                    lead.next_followup_date = when.astimezone(timezone.utc).replace(tzinfo=None) if when else None
                lead.status = LeadStatus.contacted
                session.add(lead)
                session.add(InboxEvent(**identity, kind='no_answer', actor=username, note=payload.note, next_followup_at=when))
            else:
                raise ValueError('Неизвестное действие')
            if action != 'read':
                lead.version += 1
                session.add(lead)
            await session.flush()
        return await cls.detail(session, lead_id, username=username, tenant_scope=tenant_scope)
