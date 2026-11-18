"""Tender inbox filter, scope and stored procedure identity regressions."""

from datetime import datetime, timezone

import pytest
from pydantic import ValidationError
from sqlalchemy import event
from sqlmodel import select

from core.command_actor import CommandActor
from models import LeadSource, Order, OrderStatus
from models.leads_inbox import InboxReadState, InboxTriageState
from models.tenancy import Storefront, Tenant, TenantScope
from models.tender_workflow import TenderWorkflowContext
from schemas_connector_tender_inbox import TenderInboxInput
from services.belzakupki_import_service import BelzakupkiImportService
from services.connector_tender_inbox import list_tender_inbox


SCOPE = TenantScope(1, 1)
ACTOR = CommandActor(1, "reader", SCOPE, "chatgpt")
CREATED = datetime(2026, 11, 18, 12)
FIRST = datetime(2099, 11, 20, 9, tzinfo=timezone.utc)
SECOND = datetime(2099, 11, 21, 9, tzinfo=timezone.utc)
THIRD = datetime(2099, 11, 22, 9, tzinfo=timezone.utc)


def _order(external_id, *, deadline=FIRST, location="Витебская область", **kwargs):
    tender = {
        "source": "goszakupki", "external_id": external_id, "title": "Техническое обслуживание",
        "location": location, "deadline_at": deadline.isoformat() if isinstance(deadline, datetime) else deadline,
        "estimated_value": 2065.96, "currency": "BYN",
    }
    return Order(**{
        "tenant_id": 1, "storefront_id": 1, "lead_source": LeadSource.BELZAKUPKI,
        "status": OrderStatus.NEW_LEAD, "created_at": CREATED,
        "technical_meta": {"belzakupki": {"tender": tender}}, **kwargs,
    })


@pytest.mark.asyncio
async def test_scoped_pagination_and_filters_do_not_change_inbox(db):
    db.add(Tenant(id=2, slug="foreign-tenders", display_name="Foreign tenders"))
    await db.flush()
    db.add_all([
        Storefront(id=2, tenant_id=2, slug="main", display_name="Foreign", status="active"),
        Storefront(id=3, tenant_id=1, slug="other", display_name="Other", status="active"),
    ])
    await db.flush()
    polotsk = _order("101", deadline=SECOND, location="Полоцк, Витебская область")
    vitebsk = _order("102")
    legacy_bad_date = _order("103", deadline="wrong date")
    archived = _order("104")
    legacy_lost = _order("105", status=OrderStatus.CLOSED, closing_result="lost")
    negotiation = _order("106", status=OrderStatus.NEGOTIATION)
    past = _order("107", deadline="2000-07-01T10:00:00+03:00", location="Минск")
    db.add_all([
        polotsk, vitebsk, legacy_bad_date, archived, legacy_lost, negotiation, past,
        _order("foreign", tenant_id=2, storefront_id=2),
        _order("other-store", storefront_id=3),
        _order("other-source", lead_source=LeadSource.EMAIL),
    ])
    await db.flush()
    db.add_all([
        InboxReadState(tenant_id=1, storefront_id=1, entity_kind="order", entity_id=vitebsk.id,
                       order_id=vitebsk.id, username="reader", is_read=True),
        InboxReadState(tenant_id=1, storefront_id=1, entity_kind="order", entity_id=polotsk.id,
                       order_id=polotsk.id, username="somebody-else", is_read=True),
        InboxTriageState(tenant_id=1, storefront_id=1, entity_kind="order", entity_id=archived.id,
                         order_id=archived.id, outcome="refusal", archived_at=FIRST),
        TenderWorkflowContext(tenant_id=1, storefront_id=1, order_id=polotsk.id,
                              stage="announced", deadline_manual=True, deadline_at=FIRST),
    ])
    await db.commit()

    statements = []
    connection = await db.connection()

    def observe(conn, cursor, statement, parameters, context, executemany):
        statements.append(statement)

    event.listen(connection.sync_connection, "before_cursor_execute", observe)
    try:
        page = await list_tender_inbox(db, ACTOR, TenderInboxInput(limit=2))
        assert [item.order_id for item in page.items] == [past.id, legacy_bad_date.id]
        assert page.total == 4 and page.has_more
        last = await list_tender_inbox(db, ACTOR, TenderInboxInput(limit=2, page=2))
        assert [item.order_id for item in last.items] == [vitebsk.id, polotsk.id]
        assert last.total == 4 and not last.has_more

        filtered = await list_tender_inbox(db, ACTOR, TenderInboxInput(
            region="витебская", unread=True, current_only=True, deadline_from=FIRST, deadline_to=FIRST,
        ))
        assert [item.order_id for item in filtered.items] == [polotsk.id]
        item = filtered.items[0]
        assert (item.deadline_at, item.source_deadline_at, item.deadline_basis) == (FIRST, SECOND, "workflow")
        assert item.estimated_budget == 2065.96 and item.budget_currency == "BYN"
        assert item.manager_url.endswith(f"/manager/orders/{polotsk.id}")
        none = await list_tender_inbox(db, ACTOR, TenderInboxInput(region="%"))
        assert none.total == 0

        sorted_page = await list_tender_inbox(db, ACTOR, TenderInboxInput(sort="deadline"))
        assert [item.order_id for item in sorted_page.items] == [past.id, vitebsk.id, polotsk.id, legacy_bad_date.id]
        old = await list_tender_inbox(db, ACTOR, TenderInboxInput(archived=True))
        assert [(item.order_id, item.archive_outcome) for item in old.items] == [
            (legacy_lost.id, "legacy_lost"), (archived.id, "refusal"),
        ]
        in_progress = await list_tender_inbox(db, ACTOR, TenderInboxInput(status=OrderStatus.NEGOTIATION))
        assert [item.order_id for item in in_progress.items] == [negotiation.id]
        assert all(statement.lstrip().upper().startswith("SELECT") for statement in statements)
    finally:
        event.remove(connection.sync_connection, "before_cursor_execute", observe)


def _opportunity(match_id, *, source, external_id, url, canonical, observed_at, deadline):
    return {
        "id": match_id, "updated_at": observed_at, "eligible": True,
        "relevance_status": "confirmed", "profile": {"id": 1, "name": "HVAC"},
        "tender": {
            "id": match_id, "source": source, "external_id": external_id, "title": "ТО кондиционеров",
            "customer_name": "Школа", "url": url, "canonical_url": canonical, "deadline_at": deadline.isoformat(),
        },
    }


@pytest.mark.asyncio
async def test_verified_mirror_and_corrections_preserve_separate_repeat(db):
    canonical = "https://goszakupki.by/single-source/view/101"
    original = _opportunity(
        1, source="goszakupki", external_id="101", url=canonical, canonical=canonical,
        observed_at="2026-11-10T11:00:00+00:00", deadline=FIRST,
    )
    mirror = _opportunity(
        2, source="gias", external_id="auc000101", url="https://gias.by/tenders/101?signature=secret", canonical=canonical,
        observed_at="2026-11-10T10:00:00+00:00", deadline=SECOND,
    )
    repeat_url = "https://goszakupki.by/single-source/view/102"
    repeat = _opportunity(
        3, source="goszakupki", external_id="102", url=repeat_url, canonical=repeat_url,
        observed_at="2026-11-10T11:00:00+00:00", deadline=FIRST,
    )

    async def import_items(*items):
        return await BelzakupkiImportService.import_page(
            db, tenant_scope=SCOPE, page={"items": list(items), "next_cursor": None, "has_more": False},
            cursor_before=None, now=CREATED.replace(tzinfo=timezone.utc),
        )

    await import_items(original, mirror, repeat)
    await import_items({**original, "updated_at": "2026-11-10T12:00:00+00:00",
                        "tender": {**original["tender"], "deadline_at": SECOND.isoformat()}})
    await import_items({**original, "updated_at": "2026-11-10T13:00:00+00:00",
                        "tender": {**original["tender"], "deadline_at": THIRD.isoformat()}})
    await import_items(original, mirror)

    result = await list_tender_inbox(db, ACTOR, TenderInboxInput())
    assert result.total == 2 and len({item.order_id for item in result.items}) == 2
    first = next(item for item in result.items if item.canonical_url == canonical)
    second = next(item for item in result.items if item.canonical_url == repeat_url)
    assert first.title == second.title and first.customer_name == second.customer_name
    assert first.canonical_external_id == "101" and first.procedure_kind == "single-source"
    assert first.participation_method is None
    assert [(ref.source_code, ref.external_id) for ref in first.source_references] == [
        ("goszakupki", "101"), ("gias", "auc000101"),
    ]
    assert first.source_references[1].source_url == "https://gias.by/tenders/101"
    assert first.source_references[1].source_reference == BelzakupkiImportService._order_fingerprint(
        source="gias", external_id="auc000101",
    )
    assert first.deadline_at == first.source_deadline_at == THIRD
    assert first.original_source_deadline_at == FIRST and first.previous_source_deadline_at == SECOND
    assert second.source_deadline_at == FIRST and second.original_source_deadline_at is None
    for procedure in (canonical, "auc000101"):
        exact = await list_tender_inbox(db, ACTOR, TenderInboxInput(procedure=procedure))
        assert [item.order_id for item in exact.items] == [first.order_id]
    absent = await list_tender_inbox(db, ACTOR, TenderInboxInput(procedure="auc000999"))
    assert absent.total == 0

    order = await db.scalar(select(Order).where(Order.id == first.order_id))
    snapshots = order.technical_meta["belzakupki"]["source_deadline_history"]
    assert [entry["deadline_at"] for entry in snapshots] == [FIRST.isoformat(), SECOND.isoformat()]
    assert all(entry["source"] == "goszakupki" for entry in snapshots)


def test_deadline_filter_requires_timezone_and_ordered_bounds():
    with pytest.raises(ValidationError, match="timezone"):
        TenderInboxInput(deadline_from="2099-11-20T09:00:00")
    with pytest.raises(ValidationError, match="must not be later"):
        TenderInboxInput(deadline_from=SECOND, deadline_to=FIRST)
    with pytest.raises(ValidationError, match="supported canonical"):
        TenderInboxInput(procedure="https://goszakupki.by.unrelated.test/single-source/view/101")
