"""Persistent incoming intake, retries, source provenance and concurrency."""

import asyncio
from datetime import datetime, timezone
from dataclasses import replace

import pytest
from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from core.command_actor import CommandActor
from models import Lead, Order, OrderWorkStage, PublicWriteIdempotency, StaffUser
from models.command_audit import CommandAuditEvent
from models.leads_inbox import InboxTriageState
from models.tenancy import Storefront, Tenant, TenantScope
from schemas_incoming import IncomingCreatePayload, IncomingUpdatePayload
from schemas_manager_leads import LeadUpdatePayload
from services.incoming_command_service import (
    IncomingCommandService,
    IncomingVersionConflict,
)
from services.lead_command_service import LeadCommandService
from services.public_write_idempotency_service import PublicWriteIdempotencyConflict


async def _actor(db, name="incoming-author", *, channel="chatgpt"):
    user = StaffUser(
        display_name=name, username=name, primary_role="manager", roles=["manager"]
    )
    db.add(user)
    await db.commit()
    return CommandActor(user.id, name, TenantScope(1, 1), channel)


async def _create(db, actor, *, key="incoming-request-0001", **values):
    return await IncomingCommandService.create(
        db, actor=actor, payload=IncomingCreatePayload(**values), idempotency_key=key
    )


async def _count(db, model):
    return (await db.execute(select(func.count()).select_from(model))).scalar_one()


@pytest.mark.asyncio
async def test_text_only_preserves_source_exactly_without_creating_work(db):
    actor = await _actor(db)
    text = "  Нужно обсудить кондиционер\n\tАдрес и контакт ещё уточню.  \n"
    created = await _create(db, actor, request_text=text)
    assert created.status_code == 201
    assert created.value.request_text == created.value.original_text == text
    assert created.value.intake_state == "needs_contact"
    assert created.value.missing_fields == ["contact", "address"]
    assert created.value.source_occurred_at is None
    read = await IncomingCommandService.get(
        db, actor=actor, lead_id=created.value.lead_id
    )
    assert read.model_dump() == created.value.model_dump()
    lead = await db.get(Lead, created.value.lead_id)
    assert lead.request_text == text
    assert lead.intake_meta["original_text"] == text
    assert await _count(db, Order) == 0
    assert await _count(db, OrderWorkStage) == 0


@pytest.mark.asyncio
async def test_relative_date_uses_original_message_in_its_timezone(db):
    actor = await _actor(db)
    source = datetime(2025, 12, 31, 22, 30, tzinfo=timezone.utc)
    created = await _create(
        db,
        actor,
        request_text="Клиент хочет монтаж завтра",
        requested_time_text="завтра",
        source_occurred_at=source,
        source_timezone="Europe/Minsk",
    )
    assert created.value.source_occurred_at == source
    # In Minsk the original message was already on January 1. Its tomorrow is
    # January 2, independent of the date the server processes the message.
    assert created.value.requested_at.isoformat() == "2026-01-02T00:00:00+03:00"
    assert created.value.date_precision == "date"
    assert created.value.field_sources["requested_at"] == "text"
    assert await _count(db, OrderWorkStage) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text,source",
    [
        ("Хочу завтра", None),
        ("На 31.02.2026 в 99:99", datetime(2026, 10, 6, tzinfo=timezone.utc)),
        (
            "  Позвонить когда получится, телефон пока неизвестен  ",
            datetime(2026, 10, 6, tzinfo=timezone.utc),
        ),
    ],
)
async def test_unknown_or_invalid_dates_remain_text(db, text, source):
    actor = await _actor(db)
    created = await _create(
        db,
        actor,
        request_text=text,
        requested_time_text=text,
        source_occurred_at=source,
    )
    assert created.value.requested_at is None
    assert created.value.date_precision is None
    assert created.value.original_text == created.value.request_text == text
    assert created.value.requested_time_text == text


@pytest.mark.asyncio
async def test_maximum_unicode_request_has_durable_receipt_and_replay(db):
    actor = await _actor(db)
    text = "🙂" * 12000
    first = await _create(db, actor, request_text=text)
    retry = await _create(db, actor, request_text=text)
    assert retry.replayed
    assert first.value.model_dump() == retry.value.model_dump()
    assert len(retry.value.original_text) == 12000
    assert await _count(db, Lead) == await _count(db, PublicWriteIdempotency) == 1


@pytest.mark.asyncio
async def test_same_request_key_is_isolated_by_actor_and_tenant(db):
    first_actor = await _actor(db, "incoming-author-one")
    second_actor = await _actor(db, "incoming-author-two")
    first = await _create(db, first_actor, request_text="Первый запрос")
    second = await _create(db, second_actor, request_text="Второй запрос")
    assert first.value.lead_id != second.value.lead_id
    retry = await _create(db, first_actor, request_text="Первый запрос")
    assert retry.replayed and retry.value.lead_id == first.value.lead_id
    tenant = Tenant(id=2, slug="incoming-foreign", display_name="Foreign")
    db.add(tenant)
    await db.flush()
    db.add(
        Storefront(
            id=2, tenant_id=2, slug="main", display_name="Foreign", status="active"
        )
    )
    await db.commit()
    other_scope = replace(first_actor, tenant_scope=TenantScope(2, 2))
    foreign = await _create(db, other_scope, request_text="Третий запрос")
    assert foreign.value.lead_id not in {first.value.lead_id, second.value.lead_id}
    assert await _count(db, Lead) == await _count(db, PublicWriteIdempotency) == 3


@pytest.mark.asyncio
async def test_same_source_event_deduplicates_other_key_and_rejects_different_content(
    db,
):
    actor = await _actor(db)
    first = await _create(
        db, actor, request_text="Один входящий", source_event_id="chat-message-42"
    )
    duplicate = await _create(
        db,
        actor,
        key="incoming-request-0002",
        request_text="Один входящий",
        source_event_id="chat-message-42",
    )
    assert duplicate.value.lead_id == first.value.lead_id
    assert await _count(db, Lead) == 1
    assert await _count(db, PublicWriteIdempotency) == 2
    with pytest.raises(PublicWriteIdempotencyConflict):
        await _create(
            db,
            actor,
            key="incoming-request-0003",
            request_text="Подменённый текст",
            source_event_id="chat-message-42",
        )
    assert await _count(db, Lead) == 1
    assert await _count(db, PublicWriteIdempotency) == 2
    receipts = (await db.execute(select(PublicWriteIdempotency))).scalars().all()
    assert all(row.completed_at is not None for row in receipts)
    assert "mvn_command_transaction_depth" not in db.info


@pytest.mark.asyncio
async def test_corrections_check_version_replay_and_retain_original(db):
    actor = await _actor(db)
    original = "  Клиент попросил уточнить монтаж завтра  "
    first = await _create(
        db,
        actor,
        request_text=original,
        source_occurred_at=datetime(2026, 1, 1, 8, tzinfo=timezone.utc),
    )
    payload = IncomingUpdatePayload(
        expected_version=first.value.version,
        request_text="Подтверждённые детали",
        name="Иван",
        email="client@example.test",
        address_text="Минск, ул. Тестовая 10",
        requested_time_text="завтра в 15:00",
    )
    updated = await IncomingCommandService.update(
        db,
        actor=actor,
        lead_id=first.value.lead_id,
        payload=payload,
        idempotency_key="incoming-correction-0001",
    )
    replay = await IncomingCommandService.update(
        db,
        actor=actor,
        lead_id=first.value.lead_id,
        payload=payload,
        idempotency_key="incoming-correction-0001",
    )
    assert replay.replayed and replay.value.model_dump() == updated.value.model_dump()
    assert updated.value.version == first.value.version + 1
    assert updated.value.original_text == original
    assert updated.value.request_text == "Подтверждённые детали"
    assert updated.value.intake_state == "ready_for_review"
    assert updated.value.requested_at.isoformat() == "2026-01-02T15:00:00+03:00"
    with pytest.raises(IncomingVersionConflict):
        await IncomingCommandService.update(
            db,
            actor=actor,
            lead_id=first.value.lead_id,
            payload=payload,
            idempotency_key="incoming-correction-0002",
        )
    after = await IncomingCommandService.get(
        db, actor=actor, lead_id=first.value.lead_id
    )
    assert after.version == updated.value.version
    assert after.original_text == original
    assert await _count(db, PublicWriteIdempotency) == 2
    assert await _count(db, CommandAuditEvent) == 2


@pytest.mark.asyncio
async def test_other_scope_cannot_read_or_correct_incoming(db):
    actor = await _actor(db)
    created = await _create(db, actor, request_text="Доступный только своей компании")
    db.add(Tenant(id=2, slug="incoming-scope-foreign", display_name="Foreign"))
    await db.flush()
    db.add_all(
        [
            Storefront(
                id=2, tenant_id=2, slug="main", display_name="Foreign", status="active"
            ),
            Storefront(
                id=3, tenant_id=1, slug="other", display_name="Other", status="active"
            ),
        ]
    )
    await db.commit()
    for scope in [TenantScope(2, 2), TenantScope(1, 3)]:
        foreign = replace(actor, tenant_scope=scope)
        with pytest.raises(LookupError):
            await IncomingCommandService.get(
                db, actor=foreign, lead_id=created.value.lead_id
            )
        with pytest.raises(LookupError):
            await IncomingCommandService.update(
                db,
                actor=foreign,
                lead_id=created.value.lead_id,
                payload=IncomingUpdatePayload(
                    expected_version=created.value.version,
                    request_text="Чужое изменение",
                ),
                idempotency_key="incoming-foreign-change1",
            )
        visible = await IncomingCommandService.list(db, actor=foreign)
        assert visible.total == 0 and visible.items == []
    assert (
        await IncomingCommandService.get(db, actor=actor, lead_id=created.value.lead_id)
    ).version == 1


@pytest.mark.asyncio
async def test_partial_correction_preserves_known_fields_and_explicit_null_clears(db):
    actor = await _actor(db)
    first = await _create(
        db,
        actor,
        request_text="Первоначальный запрос",
        name="Иван",
        phone="+375291234567",
        email="client@example.test",
        region_text="Минск",
        address_text="ул. Тестовая 10",
        requested_time_text="завтра в 15:00",
        source_occurred_at=datetime(2026, 1, 1, 8, tzinfo=timezone.utc),
    )
    lead = await db.get(Lead, first.value.lead_id)
    original_meta = dict(lead.intake_meta)
    payload = IncomingUpdatePayload(
        expected_version=first.value.version,
        request_text="Уточнён только текст, другой телефон в заметке +375299999999",
    )
    corrected = await IncomingCommandService.update(
        db,
        actor=actor,
        lead_id=first.value.lead_id,
        payload=payload,
        idempotency_key="incoming-partial-correction1",
    )
    before = first.value.model_dump(exclude={"version", "request_text"})
    assert corrected.value.model_dump(exclude={"version", "request_text"}) == before
    assert (await db.get(Lead, first.value.lead_id)).intake_meta == original_meta
    replay = await IncomingCommandService.update(
        db,
        actor=actor,
        lead_id=first.value.lead_id,
        payload=payload,
        idempotency_key="incoming-partial-correction1",
    )
    assert replay.replayed and replay.value == corrected.value
    # Omission and explicit null have different effects, so cannot share a key.
    with pytest.raises(PublicWriteIdempotencyConflict):
        await IncomingCommandService.update(
            db,
            actor=actor,
            lead_id=first.value.lead_id,
            payload=payload.model_copy(update={"phone": None}),
            idempotency_key="incoming-partial-correction1",
        )
    cleared = await IncomingCommandService.update(
        db,
        actor=actor,
        lead_id=first.value.lead_id,
        payload=IncomingUpdatePayload(
            expected_version=corrected.value.version,
            request_text=corrected.value.request_text,
            phone=None,
            address_text=None,
            requested_at=None,
        ),
        idempotency_key="incoming-explicit-clear-0001",
    )
    assert cleared.value.phone is None and cleared.value.address_text is None
    assert cleared.value.requested_at is None and cleared.value.date_precision is None
    assert cleared.value.email == first.value.email
    assert cleared.value.requested_time_text == first.value.requested_time_text
    assert "phone" not in cleared.value.field_sources
    assert "address_text" not in cleared.value.field_sources
    assert "requested_at" not in cleared.value.field_sources


@pytest.mark.asyncio
@pytest.mark.parametrize("source_known", [True, False])
async def test_changed_time_wish_replaces_suggestion_using_retained_source(
    db, source_known
):
    actor = await _actor(db)
    first = await _create(
        db,
        actor,
        request_text="Монтаж завтра",
        requested_time_text="завтра",
        requested_at=datetime(2026, 1, 2, 8, tzinfo=timezone.utc),
        source_occurred_at=(
            datetime(2026, 1, 1, 8, tzinfo=timezone.utc) if source_known else None
        ),
    )
    current = first.value
    for index, wish in enumerate(["послезавтра в 15:00", "когда получится", None]):
        corrected = await IncomingCommandService.update(
            db,
            actor=actor,
            lead_id=first.value.lead_id,
            payload=IncomingUpdatePayload(
                expected_version=current.version,
                request_text=current.request_text,
                requested_time_text=wish,
            ),
            idempotency_key=f"incoming-changed-time-000{index}",
        )
        current = corrected.value
        assert current.source_occurred_at == first.value.source_occurred_at
        if index == 0 and source_known:
            assert current.requested_at.isoformat() == "2026-01-03T15:00:00+03:00"
            assert current.date_precision == "datetime"
            assert current.field_sources["requested_at"] == "text"
        else:
            assert current.requested_at is None and current.date_precision is None
            assert "requested_at" not in current.field_sources


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal", ["archived", "triage_archived", "converted"])
async def test_archived_or_converted_incoming_cannot_be_corrected(db, terminal):
    actor = await _actor(db)
    created = await _create(db, actor, request_text="Обращение обработано")
    lead = await db.get(Lead, created.value.lead_id)
    if terminal == "archived":
        lead.archived_at = datetime.now()
    elif terminal == "triage_archived":
        db.add(
            InboxTriageState(
                entity_kind="lead",
                entity_id=lead.id,
                lead_id=lead.id,
                tenant_id=1,
                storefront_id=1,
                archived_at=datetime.now(),
            )
        )
    else:
        order = Order(tenant_id=1, storefront_id=1, title="Converted incoming")
        db.add(order)
        await db.flush()
        lead.converted_order_id = order.id
    await db.commit()
    with pytest.raises((LookupError, IncomingVersionConflict, PermissionError)):
        await IncomingCommandService.update(
            db,
            actor=actor,
            lead_id=created.value.lead_id,
            payload=IncomingUpdatePayload(
                expected_version=created.value.version,
                request_text="Неожиданная правка",
            ),
            idempotency_key="incoming-terminal-change1",
        )
    assert (await IncomingCommandService.list(db, actor=actor)).items == []
    current = await IncomingCommandService.get(
        db, actor=actor, lead_id=created.value.lead_id
    )
    assert current.version == created.value.version
    assert current.request_text == "Обращение обработано"


@pytest.mark.asyncio
async def test_legacy_manager_correction_invalidates_connector_expected_version(db):
    actor = await _actor(db)
    created = await _create(db, actor, request_text="Первоначальные данные")
    await LeadCommandService.update_lead(
        db,
        created.value.lead_id,
        LeadUpdatePayload(name="Уточнено менеджером"),
        tenant_scope=actor.tenant_scope,
    )
    with pytest.raises(IncomingVersionConflict):
        await IncomingCommandService.update(
            db,
            actor=actor,
            lead_id=created.value.lead_id,
            payload=IncomingUpdatePayload(
                expected_version=created.value.version, request_text="Устаревшая правка"
            ),
            idempotency_key="incoming-stale-legacy-edit1",
        )
    current = await IncomingCommandService.get(
        db, actor=actor, lead_id=created.value.lead_id
    )
    assert current.version == created.value.version + 1
    assert current.name == "Уточнено менеджером"
    assert current.request_text == "Первоначальные данные"


@pytest.mark.asyncio
@pytest.mark.parametrize("same_key", [True, False])
async def test_concurrent_delivery_across_physical_connections_creates_one_lead(
    db_engine, same_key
):
    async with AsyncSession(db_engine, expire_on_commit=False) as setup:
        actor = await _actor(setup, "incoming-concurrent")
    payload = IncomingCreatePayload(
        request_text="Одновременное обращение", source_event_id="external-message-42"
    )
    gate = asyncio.Event()

    async def delivery(key):
        async with AsyncSession(db_engine, expire_on_commit=False) as session:
            await gate.wait()
            outcome = await IncomingCommandService.create(
                session, actor=actor, payload=payload, idempotency_key=key
            )
            assert not session.in_transaction()
            assert "mvn_command_transaction_depth" not in session.info
            return outcome

    first_key = "incoming-simultaneous-0001"
    jobs = [
        asyncio.create_task(delivery(first_key)),
        asyncio.create_task(
            delivery(first_key if same_key else "incoming-simultaneous-0002")
        ),
    ]
    gate.set()
    first, second = await asyncio.wait_for(asyncio.gather(*jobs), timeout=10)
    assert first.value.lead_id == second.value.lead_id
    if same_key:
        assert sorted([first.replayed, second.replayed]) == [False, True]
    async with AsyncSession(db_engine) as check:
        assert await _count(check, Lead) == 1
        assert await _count(check, PublicWriteIdempotency) == (1 if same_key else 2)
        receipts = (await check.execute(select(PublicWriteIdempotency))).scalars().all()
        assert all(row.completed_at is not None for row in receipts)


@pytest.mark.asyncio
@pytest.mark.parametrize("text", [
    "ТО не завтра, дату уточнить",
    "ТО завтра или послезавтра в 09:00",
    "ТО завтра; созвониться сегодня в 18:00",
    "ТО через месяц, звонок завтра в 09:00",
])
async def test_ambiguous_create_and_changed_wish_abstain_with_stable_replay(db, monkeypatch, text):
    from models.personal_task import PersonalTask
    import services.incoming_command_service as module

    class LaterClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2030, 1, 1, tzinfo=timezone.utc).astimezone(tz)

    actor = await _actor(db)
    source = datetime(2026, 10, 7, 19, 30, tzinfo=timezone.utc)
    created = await _create(db, actor, request_text=text, source_occurred_at=source)
    assert created.value.requested_at is created.value.date_precision is None
    assert created.value.request_text == created.value.original_text == text
    assert "requested_at" not in created.value.field_sources
    monkeypatch.setattr(module, "datetime", LaterClock)
    replay = await _create(db, actor, request_text=text, source_occurred_at=source)
    assert replay.replayed and replay.value == created.value
    positive_payload = IncomingUpdatePayload(expected_version=1, request_text=text, requested_time_text="ТО завтра в 09:00")
    positive = await IncomingCommandService.update(db, actor=actor, lead_id=created.value.lead_id,
        payload=positive_payload, idempotency_key="date-positive-wish-0001")
    assert positive.value.requested_at.isoformat() == "2026-10-08T09:00:00+03:00"
    assert positive.value.date_precision == "datetime"
    payload = IncomingUpdatePayload(expected_version=2, request_text=text, requested_time_text=text)
    changed = await IncomingCommandService.update(db, actor=actor, lead_id=created.value.lead_id,
        payload=payload, idempotency_key="date-ambiguous-wish-0001")
    retry = await IncomingCommandService.update(db, actor=actor, lead_id=created.value.lead_id,
        payload=payload, idempotency_key="date-ambiguous-wish-0001")
    assert retry.replayed and retry.value == changed.value
    assert changed.value.requested_at is changed.value.date_precision is None
    assert changed.value.requested_time_text == changed.value.original_text == text
    assert changed.value.source_occurred_at == source
    assert changed.value.source_timezone == "Europe/Minsk"
    assert "requested_at" not in changed.value.field_sources
    assert changed.value.version == 3
    assert await _count(db, Lead) == 1
    assert await _count(db, PublicWriteIdempotency) == 3
    assert await _count(db, Order) == await _count(db, OrderWorkStage) == await _count(db, PersonalTask) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("zone,expected", [
    ("Asia/Tokyo", "2026-10-09T09:00:00+09:00"),
    ("America/Los_Angeles", "2026-10-08T09:00:00-07:00"),
])
async def test_delayed_replay_and_correction_use_the_source_timezone(db, monkeypatch, zone, expected):
    import services.incoming_command_service as module

    class LaterClock(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2030, 1, 1, tzinfo=timezone.utc).astimezone(tz)

    actor = await _actor(db)
    source = datetime(2026, 10, 7, 22, 30, tzinfo=timezone.utc)
    values = dict(request_text="ТО завтра в 09:00", source_occurred_at=source, source_timezone=zone)
    created = await _create(db, actor, **values)
    assert created.value.requested_at.isoformat() == expected
    monkeypatch.setattr(module, "datetime", LaterClock)
    replay = await _create(db, actor, **values)
    assert replay.replayed and replay.value == created.value
    corrected = await IncomingCommandService.update(db, actor=actor, lead_id=created.value.lead_id,
        payload=IncomingUpdatePayload(expected_version=1, request_text="ТО дату уточнить", requested_time_text="завтра в 09:00"),
        idempotency_key="date-delayed-correction1")
    assert corrected.value.requested_at.isoformat() == expected
    assert corrected.value.source_occurred_at == source
    assert corrected.value.source_timezone == zone
    assert corrected.value.original_text == values["request_text"]
