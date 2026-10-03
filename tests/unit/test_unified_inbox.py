from datetime import datetime, timedelta, timezone
import pytest
from models import Lead, LeadStatus, Order, OrderStatus
from models.leads_inbox import InboxTriageState
from schemas_leads_inbox import InboxArchivePayload, InboxReadPayload, InboxNoAnswerPayload
from schemas_manager_leads import LeadQualifyPayload
from services.raw_lead_inbox_service import RawLeadInboxService
from services.unified_inbox_service import UnifiedInboxService
from services.lead_service import LeadService


@pytest.mark.asyncio
async def test_mixed_pagination_personal_read_and_native_identity(db, tenant_scope):
    when = datetime(2026, 10, 1, 12)
    lead = Lead(tenant_id=1, storefront_id=1, source='site', name='Иван', request_text='Нужен монтаж', created_at=when)
    order = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD, title='Поставка', created_at=when + timedelta(minutes=1))
    qualified = Lead(tenant_id=1, storefront_id=1, source='bot', status=LeadStatus.qualified, request_text='Уже взяли')
    db.add_all([lead, order, qualified])
    await db.commit()
    first = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, limit=1)
    second = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, limit=1, page=2)
    assert first.total == second.total == 2
    assert first.items[0].entity_kind == 'order'
    assert second.items[0].entity_kind == 'lead'
    await RawLeadInboxService.mutate(db, lead.id, username='a', tenant_scope=tenant_scope, action='read', payload=InboxReadPayload(is_read=True))
    assert (await UnifiedInboxService.counts(db, username='a', tenant_scope=tenant_scope)).count == 1
    assert (await UnifiedInboxService.counts(db, username='b', tenant_scope=tenant_scope)).count == 2
    filtered = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, source='site', unread_only=True)
    assert filtered.total == 0
    searched = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, search='монтаж')
    assert searched.total == 1 and searched.items[0].id == lead.id


@pytest.mark.asyncio
async def test_source_counts_cover_the_queue_before_source_filter_and_pagination(db, tenant_scope):
    site = Lead(tenant_id=1, storefront_id=1, source='site', request_text='Монтаж')
    rows = [site,
        Lead(tenant_id=1, storefront_id=1, source='email', request_text='Монтаж'),
        Order(tenant_id=1, storefront_id=1, lead_source='email', title='Поставка'),
        Order(tenant_id=1, storefront_id=1, lead_source='phone', title='Доставка'),
        Lead(tenant_id=1, storefront_id=1, source='bot', status=LeadStatus.lost, request_text='Монтаж'),
        Lead(tenant_id=1, storefront_id=1, source='manager', status=LeadStatus.qualified, request_text='Монтаж')]
    db.add_all(rows)
    await db.commit()
    first = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, source='email', limit=1)
    second = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, source='email', limit=1, page=2)
    assert first.total == second.total == 2
    assert first.source_counts == second.source_counts == {'site': 1, 'email': 2, 'phone': 1}
    assert len(first.items) == len(second.items) == 1
    searched = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, search='монтаж')
    assert searched.source_counts == {'site': 1, 'email': 1}
    await RawLeadInboxService.mutate(db, site.id, username='a', tenant_scope=tenant_scope,
        action='read', payload=InboxReadPayload(is_read=True))
    unread = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, search='монтаж', unread_only=True)
    other_reader = await UnifiedInboxService.get_leads_inbox(db, username='b', tenant_scope=tenant_scope, search='монтаж', unread_only=True)
    assert unread.source_counts == {'email': 1}
    assert other_reader.source_counts == {'site': 1, 'email': 1}
    archive = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, scope='archive')
    assert archive.source_counts == {'bot': 1}
    empty = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, search='нет совпадений')
    assert empty.source_counts == {} and empty.total == 0


@pytest.mark.asyncio
async def test_source_counts_and_other_filter_include_unknown_historical_sources(db, tenant_scope):
    db.add_all([
        Order(tenant_id=1, storefront_id=1, lead_source=None),
        Lead(tenant_id=1, storefront_id=1, source='legacy', request_text='Монтаж'),
        Lead(tenant_id=1, storefront_id=1, source='other', request_text='Поставка'),
        Lead(tenant_id=1, storefront_id=1, source='site', request_text='Заявка')])
    await db.commit()
    result = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, source='other')
    assert result.source_counts == {'site': 1, 'other': 3}
    assert result.total == len(result.items) == 3


@pytest.mark.asyncio
async def test_source_counts_keep_tenant_and_storefront_boundaries(db, tenant_scope):
    from models.tenancy import Storefront, Tenant

    tenant = Tenant(slug='inbox-counts-foreign', display_name='Foreign')
    db.add(tenant)
    await db.flush()
    foreign = Storefront(tenant_id=tenant.id, slug='main', display_name='Foreign')
    sibling = Storefront(tenant_id=1, slug='inbox-counts-sibling', display_name='Sibling')
    db.add_all([foreign, sibling])
    await db.flush()
    db.add_all([
        Lead(tenant_id=1, storefront_id=1, source='site', request_text='Своя заявка'),
        Order(tenant_id=1, storefront_id=1, lead_source='email'),
        Lead(tenant_id=1, storefront_id=sibling.id, source='site', request_text='Другая витрина'),
        Order(tenant_id=1, storefront_id=sibling.id, lead_source='email'),
        Lead(tenant_id=tenant.id, storefront_id=foreign.id, source='phone', request_text='Другой арендатор'),
        Order(tenant_id=tenant.id, storefront_id=foreign.id, lead_source='bot')])
    await db.commit()
    result = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope)
    assert result.source_counts == {'site': 1, 'email': 1}
    assert result.total == 2


@pytest.mark.asyncio
async def test_raw_archive_restore_does_not_create_customer_or_qualify(db, tenant_scope):
    lead = Lead(tenant_id=1, storefront_id=1, source='site', request_text='Монтаж', name='Иван')
    db.add(lead)
    await db.commit()
    result = await RawLeadInboxService.mutate(db, lead.id, username='a', tenant_scope=tenant_scope, action='archive',
        payload=InboxArchivePayload(outcome='refusal', reason='capacity'))
    assert result.archive.reason == 'capacity'
    assert (await UnifiedInboxService.counts(db, username='a', tenant_scope=tenant_scope)).pending_count == 0
    with pytest.raises(ValueError, match='архиве'):
        await LeadService.qualify_lead(db, lead.id, LeadQualifyPayload(name='Иван', customer_type='individual', workflow_type='sales_installation'), tenant_scope=tenant_scope)
    restored = await RawLeadInboxService.mutate(db, lead.id, username='a', tenant_scope=tenant_scope, action='restore')
    assert restored.archive is None and restored.customer_id is None
    assert [item.kind for item in restored.history] == ['restore', 'archive']
    assert (await UnifiedInboxService.counts(db, username='a', tenant_scope=tenant_scope)).pending_count == 1


@pytest.mark.asyncio
async def test_raw_next_contact_and_scope(db, tenant_scope):
    lead = Lead(tenant_id=1, storefront_id=1, source='site', request_text='Монтаж')
    db.add(lead)
    await db.commit()
    when = datetime(2026, 10, 8, 10, tzinfo=timezone(timedelta(hours=3)))
    result = await RawLeadInboxService.mutate(db, lead.id, username='a', tenant_scope=tenant_scope, action='no-answer',
        payload=InboxNoAnswerPayload(next_followup_at=when))
    assert result.no_answer_count == 1
    assert result.next_followup_at == datetime(2026, 10, 8, 7, tzinfo=timezone.utc)
    from dataclasses import replace
    with pytest.raises(LookupError):
        await RawLeadInboxService.detail(db, lead.id, username='a', tenant_scope=replace(tenant_scope, tenant_id=999))


@pytest.mark.asyncio
async def test_same_procurement_exposes_prior_decision_without_auto_archiving(db, tenant_scope):
    from services.leads_inbox_command_service import LeadsInboxCommandService
    old = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD, lead_source='belzakupki',
        title='Кондиционеры', technical_meta={'belzakupki': {'tender': {'url': 'https://goszakupki.by/marketing/view/3705549'}}})
    new = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD, lead_source='email',
        comment='Просим предложение https://goszakupki.by/marketing/view/3705549?utm_source=mail')
    db.add_all([old, new])
    await db.commit()
    await LeadsInboxCommandService.archive(db, order_id=old.id, username='a', tenant_scope=tenant_scope,
        payload=InboxArchivePayload(outcome='refusal', reason='terms'))
    result = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope)
    assert result.total == 1
    assert result.items[0].related_requests[0].order_id == old.id
    assert result.items[0].related_requests[0].reason == 'terms'
    assert result.items[0].archive is None


@pytest.mark.asyncio
async def test_raw_no_answer_count_includes_attempts_older_than_history_page(db, tenant_scope):
    from models.leads_inbox import InboxEvent

    lead = Lead(tenant_id=1, storefront_id=1, source='site', request_text='Перезвонить')
    db.add(lead)
    await db.flush()
    db.add_all([InboxEvent(entity_kind='lead', entity_id=lead.id, lead_id=lead.id,
        tenant_id=1, storefront_id=1, kind='no_answer', actor='a') for _ in range(110)])
    await db.commit()
    result = await RawLeadInboxService.detail(db, lead.id, username='a', tenant_scope=tenant_scope)
    assert result.no_answer_count == 110 and len(result.history) == 100
    page = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope)
    assert page.items[0].no_answer_count == result.no_answer_count


def test_procurement_url_projection_ignores_malformed_historical_metadata():
    from services.inbox_source_relations import procurement_urls

    order = Order(tenant_id=1, storefront_id=1, technical_meta={'belzakupki': 'invalid', 'email_source_text': 42},
        comment='Запрос https://goszakupki.by/marketing/view/3705549')
    assert procurement_urls(order) == {'goszakupki.by/marketing/view/3705549'}


@pytest.mark.asyncio
async def test_raw_restore_keeps_legacy_reason_and_archive_date_in_history(db, tenant_scope):
    from models import LeadLossReason

    archived_at = datetime(2026, 9, 1, 12)
    reason = next(iter(LeadLossReason))
    lead = Lead(tenant_id=1, storefront_id=1, source='site', request_text='Монтаж',
        status=LeadStatus.lost, loss_reason=reason, archived_at=archived_at)
    db.add(lead)
    await db.commit()
    result = await RawLeadInboxService.mutate(db, lead.id, username='a', tenant_scope=tenant_scope, action='restore')
    event = result.history[0]
    assert event.outcome == 'legacy_lost' and event.reason == reason.value
    assert reason.value in event.note and archived_at.isoformat() in event.note
    assert result.archive is None


@pytest.mark.asyncio
async def test_mixed_deadline_sort_uses_small_fields_and_ignores_non_submission_dates(db, tenant_scope):
    from sqlalchemy import event

    rows = [
        Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD, lead_source='belzakupki',
            technical_meta={'belzakupki': {'tender': {'deadline_at': '2026-10-03T12:00:00Z'}}}),
        Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD, lead_source='email',
            technical_meta={'email_source_text': 'x' * 180000, 'inbox_tender': {
                'confirmed': True, 'is_tender': True, 'deadline_at': '2026-10-03T13:00:00+03:00',
                'confirmed_by': 'a', 'confirmed_at': '2026-10-01T00:00:00Z'}}),
        Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD, lead_source='belzakupki',
            technical_meta={'belzakupki': {'tender': {'deadline_at': '2026-09-01T00:00:00Z', 'deadline_kind': 'delivery'}}}),
        Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD, lead_source='email',
            technical_meta={'inbox_tender': {'confirmed': 'invalid', 'is_tender': {}, 'deadline_at': 'broken'}}),
        Lead(tenant_id=1, storefront_id=1, source='site', request_text='Монтаж'),
    ]
    db.add_all(rows)
    await db.commit()
    statements = []
    connection = await db.connection()
    def capture(connection, cursor, statement, parameters, context, executemany):
        statements.append(statement)
    event.listen(connection.sync_connection, 'before_cursor_execute', capture)
    try:
        first = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, sort='deadline', limit=1)
        second = await UnifiedInboxService.get_leads_inbox(db, username='a', tenant_scope=tenant_scope, sort='deadline', limit=1, page=2)
    finally:
        event.remove(connection.sync_connection, 'before_cursor_execute', capture)
    assert first.total == second.total == 5
    assert first.items[0].id == rows[1].id and second.items[0].id == rows[0].id
    root_queries = [text for text in statements if 'manual_deadline_at' in text]
    assert root_queries
    # Sorting roots return only scalar deadline fields. The large original text
    # stays in the selected detail row, rather than every sorting candidate.
    assert all('CAST("order".technical_meta AS VARCHAR)' not in text for text in root_queries)
