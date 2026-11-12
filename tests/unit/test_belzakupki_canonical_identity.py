from copy import deepcopy

import pytest
from sqlalchemy.orm import lazyload
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import select

from models import LeadSource, Order, OrderStatus
from services.belzakupki_canonical_identity import canonical_procurement_url
from services.belzakupki_import_service import BelzakupkiImportResult, BelzakupkiImportService as Importer
from services.tenant_scope_service import TenantScope

URL = "https://goszakupki.by/single-source/view/3837629"
SCOPE = TenantScope(tenant_id=1, storefront_id=1, is_system=True, is_canonical_storefront=True)


def item(mirror=False, match=1, canonical=True):
    tender = {"source": "gias_by" if mirror else "goszakupki_by", "external_id": "gias-1" if mirror else "3837629",
              "title": "Same title", "url": "https://gias.by/tenders/hash" if mirror else URL}
    if canonical:
        tender["canonical_url"] = URL
    return {"id": match, "updated_at": "2026-11-12T10:00:00Z", "profile": {"id": match, "name": "HVAC"},
            "eligible": True, "relevance_status": "confirmed", "tender": tender}


@pytest.mark.parametrize("url,expected", [
    ("http://www.goszakupki.by:80/single-source/view/3837629/?tracking=1#x", URL),
    ("https://goszakupki.by/marketing/view/3837629", "https://goszakupki.by/marketing/view/3837629"),
    ("https://goszakupki.by.evil.test/single-source/view/3837629", None),
    ("https://user@goszakupki.by/single-source/view/3837629", None),
    ("https://goszakupki.by:444/single-source/view/3837629", None),
    ("https://goszakupki.by/", None),
    ("https://goszakupki.by/files/view/3837629", None),
    ("https://goszakupki.by\\evil/single-source/view/3837629", None),
    ("https://zakupki.butb.by/auctions/viewinvitation.html?auction=a&auction=b", None),
    ("https://zakupki.butb.by/auctions/viewinvitation.html?auction=a&auction=", None),
])
def test_exact_url_identity(url, expected):
    assert canonical_procurement_url(url) == expected


@pytest.fixture
async def isolated_orders(monkeypatch):
    from services.communications.incoming_events import IncomingEventService
    events = []
    async def enqueue(session, order):
        events.append(order.id)
    monkeypatch.setattr(IncomingEventService, "enqueue_order", enqueue)
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Order.__table__.create)
    async with async_sessionmaker(engine, expire_on_commit=False)() as session:
        yield session, events
    await engine.dispose()


async def ingest(session, source, scope=SCOPE):
    result = BelzakupkiImportResult()
    await Importer._upsert_opportunity(session, tenant_scope=scope, item=source, result=result, allow_create=True)
    await session.flush()
    return result


@pytest.mark.asyncio
@pytest.mark.parametrize("mirror_first", [False, True])
async def test_original_and_mirror_share_order_and_preserve_evidence(isolated_orders, mirror_first):
    session, events = isolated_orders
    first = await ingest(session, item(mirror_first))
    order = await session.get(Order, first.order_id, options=[lazyload("*")])
    order.title, order.comment, order.status = "Staff", "Reviewed", OrderStatus.NEGOTIATION
    meta = deepcopy(order.technical_meta)
    meta["belzakupki"]["enrichment"] = {"reviewed": True}
    order.technical_meta = meta
    second = await ingest(session, item(not mirror_first, 2))
    replay = await ingest(session, item(mirror_first, 1, canonical=False))
    orders = (await session.execute(select(Order).options(lazyload("*")))).scalars().all()
    assert len(orders) == 1 and len(events) == 1
    assert first.order_id == second.order_id == replay.order_id
    assert (order.title, order.comment, order.status) == ("Staff", "Reviewed", OrderStatus.NEGOTIATION)
    provider = order.technical_meta["belzakupki"]
    assert len(provider["source_references"]) == 2 and len(provider["matches"]) == 2
    assert provider["enrichment"] == {"reviewed": True}
    assert provider["source"] == provider["tender"]["source"]
    assert provider["external_tender_id"] == provider["tender"]["external_id"]
    assert provider["canonical_url"] == URL


@pytest.mark.asyncio
async def test_different_routes_and_tenant_scopes_remain_separate(isolated_orders):
    session, events = isolated_orders
    await ingest(session, item())
    different = item(match=2)
    different["tender"].update(source="gias_by", external_id="other", canonical_url=URL.replace("single-source", "marketing"))
    await ingest(session, different)
    await ingest(session, item(), TenantScope(tenant_id=2, storefront_id=2))
    assert len((await session.execute(select(Order).options(lazyload("*")))).scalars().all()) == 3
    assert len(events) == 3


@pytest.mark.asyncio
@pytest.mark.parametrize("two_existing", [False, True])
async def test_adopts_legacy_order_without_creating_or_deleting_duplicates(isolated_orders, two_existing):
    session, events = isolated_orders
    original = item(canonical=False)
    legacy = Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEGOTIATION, lead_source=LeadSource.BELZAKUPKI,
                   source_fingerprint=Importer._order_fingerprint(source="goszakupki_by", external_id="3837629"),
                   technical_meta={"belzakupki": {"tender": original["tender"], "enrichment": {"reviewed": True}}})
    session.add(legacy)
    if two_existing:
        session.add(Order(tenant_id=1, storefront_id=1, status=OrderStatus.NEW_LEAD, lead_source=LeadSource.BELZAKUPKI,
                    source_fingerprint=Importer._order_fingerprint(source="gias_by", external_id="gias-1"),
                    technical_meta={"belzakupki": {"tender": item(True, canonical=False)["tender"]}}))
    await session.flush()
    outcome = await ingest(session, item(True, 2))
    assert outcome.order_id == legacy.id and outcome.created == 0 and events == []
    assert len((await session.execute(select(Order).options(lazyload("*")))).scalars().all()) == (2 if two_existing else 1)
    assert legacy.status == OrderStatus.NEGOTIATION
    if two_existing:
        assert legacy.technical_meta["belzakupki"]["identity_conflicts"]


@pytest.mark.asyncio
@pytest.mark.parametrize("mirror", [False, True])
async def test_legacy_original_number_with_different_route_does_not_merge(isolated_orders, mirror):
    session, _ = isolated_orders
    session.add(Order(tenant_id=1, storefront_id=1, lead_source=LeadSource.BELZAKUPKI,
                source_fingerprint=Importer._order_fingerprint(source="goszakupki_by", external_id="3837629"),
                technical_meta={"belzakupki": {"tender": {**item()["tender"], "canonical_url": None,
                    "url": URL.replace("single-source", "marketing")}}}))
    await session.flush()
    outcome = await ingest(session, item(mirror))
    assert outcome.created == 1
    assert len((await session.execute(select(Order).options(lazyload("*")))).scalars().all()) == 2


@pytest.mark.asyncio
async def test_stale_native_update_can_adopt_identity_without_losing_newer_match(isolated_orders):
    session, events = isolated_orders
    source = item(True, canonical=False)
    source["updated_at"] = "2026-11-12T12:00:00Z"
    first = await ingest(session, source)
    adopted = await ingest(session, item(True))
    replay = await ingest(session, source)
    original = await ingest(session, item(False, 2))
    assert first.order_id == adopted.order_id == replay.order_id == original.order_id
    assert len(events) == 1
    order = (await session.execute(select(Order).options(lazyload("*")))).scalar_one()
    assert order.technical_meta["belzakupki"]["matches"]["1"]["updated_at"] == "2026-11-12T12:00:00+00:00"


@pytest.mark.asyncio
async def test_two_native_gos_routes_with_same_number_remain_distinct(isolated_orders):
    session, events = isolated_orders
    first = await ingest(session, item())
    other = item(match=2)
    other["tender"].update(url=URL.replace("single-source", "marketing"),
                           canonical_url=URL.replace("single-source", "marketing"))
    second = await ingest(session, other)
    assert first.order_id != second.order_id and len(events) == 2


@pytest.mark.parametrize("value,expected", [
    (" \u00a0http://www.goszakupki.by/limited/view/3836760/ ", "https://goszakupki.by/limited/view/3836760"),
    ("\thttps://goszakupki.by/limited/view/3836760", None),
    ("https://goszakupki.by/limited/view/3836760\n", None),
    ("https://goszakupki.by/limited/view/3836760\x7f", None),
    ("https://goszakupki.by/limited/view/3836760//", None),
    ("https://icetrade.by/tenders/all/view/1407896//", None),
    ("https://zakupki.butb.by/auctions/viewinvitation.html/?auction=42", None),
])
def test_url_normalization_matches_producer(value, expected):
    assert canonical_procurement_url(value) == expected


@pytest.mark.asyncio
@pytest.mark.parametrize("mirror_first", [False, True])
async def test_real_icetrade_limited_gos_pair_is_one_incoming(isolated_orders, mirror_first):
    session, events = isolated_orders
    original_url = "https://goszakupki.by/limited/view/3836760"
    original = item(match=1)
    original["tender"].update(source="goszakupki_by", external_id="3836760", url=original_url, canonical_url=original_url)
    mirror = item(True, 2)
    mirror["tender"].update(source="icetrade_by", external_id="1407896",
                            url="https://icetrade.by/tenders/all/view/1407896", canonical_url=original_url)
    first, second = (mirror, original) if mirror_first else (original, mirror)
    first_result = await ingest(session, first)
    second_result = await ingest(session, second)
    assert first_result.order_id == second_result.order_id and len(events) == 1
    order = (await session.execute(select(Order).options(lazyload("*")))).scalar_one()
    refs = order.technical_meta["belzakupki"]["source_references"]
    assert {reference["url"] for reference in refs.values()} == {original_url, mirror["tender"]["url"]}


@pytest.mark.asyncio
@pytest.mark.parametrize("mirror_source", ["gias_by", "icetrade_by"])
@pytest.mark.parametrize("other_original_exists", [False, True])
async def test_conflicting_original_cannot_duplicate_or_steal_linked_mirror(isolated_orders, mirror_source, other_original_exists):
    session, events = isolated_orders
    mirror = item(True)
    mirror["tender"]["source"] = mirror_source
    if mirror_source == "icetrade_by":
        mirror["tender"].update(external_id="1407896", url="https://icetrade.by/tenders/all/view/1407896")
    initial = await ingest(session, mirror)
    other_url = "https://goszakupki.by/limited/view/3836760"
    if other_original_exists:
        original = item(match=3)
        original["tender"].update(external_id="3836760", url=other_url, canonical_url=other_url)
        other = await ingest(session, original)
        assert other.order_id != initial.order_id
    conflicting = deepcopy(mirror)
    conflicting.update(id=2, updated_at="2026-11-12T11:00:00Z")
    conflicting["tender"]["canonical_url"] = other_url
    result = await ingest(session, conflicting)
    repeated = await ingest(session, conflicting)
    assert repeated.created == 0
    replay = deepcopy(conflicting)
    replay["tender"]["canonical_url"] = None
    replay_result = await ingest(session, replay)
    assert result.order_id == replay_result.order_id == initial.order_id
    orders = (await session.execute(select(Order).options(lazyload("*")))).scalars().all()
    assert len(orders) == len(events) == (2 if other_original_exists else 1)
    chosen = next(order for order in orders if order.id == initial.order_id)
    metadata = chosen.technical_meta["belzakupki"]
    assert metadata["canonical_url"] == URL
    assert metadata["canonical_conflicts"] == sorted([URL, other_url])
    assert metadata["matches"]["2"]["tender"]["claimed_canonical_url"] == other_url
    if other_original_exists:
        assert metadata["identity_conflicts"] == [other.order_id]
