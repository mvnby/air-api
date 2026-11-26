from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import httpx
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from models import Tenant, TenantTenderModule, TenderMarketCheckpoint, TenderMarketEvidence, TenderMarketPublication
from models.tenancy import TenantScope
from schemas_tender_market import MarketPageInput
from schemas_tender_search import TenderPlace, TenderSearchProfile
from services import tender_market_sync_service
from services import tender_market_evidence_service as verification
from services import tender_document_reader, tender_qualification
from services.belzakupki_enrichment_service import BelzakupkiEnrichmentService
from services.tender_market_evidence_service import TenderMarketEvidenceService as Evidence
from services.tender_market_service import TenderMarketService
from services.tender_market_source import market_original_inventory
from services.tender_market_sync_service import TenderMarketSyncService
from services.tender_module_service import TenderModuleError


@pytest_asyncio.fixture
async def database():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(lambda db: SQLModel.metadata.create_all(db, tables=[
            Tenant.__table__, TenantTenderModule.__table__,
            TenderMarketCheckpoint.__table__, TenderMarketPublication.__table__, TenderMarketEvidence.__table__,
        ]))
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        session.add(TenderMarketCheckpoint(id=1))
        for company_id in (11, 12, 13):
            session.add(Tenant(id=company_id, slug=f"company-{company_id}", display_name=f"Компания {company_id}"))
    yield sessions
    await engine.dispose()


def notice(number, title, *, place="Витебская область, г. Витебск", at=None, active=True, lots=None, host="goszakupki.by"):
    return {
        "source": "goszakupki_by", "external_id": str(number),
        "url": f"https://{host}/single-source/view/{number}",
        "title": title, "updated_at": at or datetime.now(timezone.utc), "active": active,
        "lots": lots if lots is not None else [{"number": "1", "name": title, "delivery_place": place}],
        "lot_inventory_complete": True,
    }


async def put(database, token, *items, next_cursor=None):
    async with database.begin() as session:
        return await TenderMarketSyncService.store_page(session, token, MarketPageInput(
            items=list(items), has_more=next_cursor is not None, next_cursor=next_cursor,
        ))


@pytest.mark.asyncio
async def test_market_sweep_is_resumable_and_retires_only_after_completion(database):
    at = datetime(2026, 11, 26, tzinfo=timezone.utc)
    first = notice(1, "Поставка кондиционеров", at=at)
    second = notice(2, "Монтаж вентиляции", at=at)
    assert await put(database, (None, 1), first, second)
    assert not await put(database, (None, 1), second)
    assert await put(database, (None, 2), {**first, "title": "Устаревшее название", "updated_at": at - timedelta(days=1)},
                     notice(3, "Недоверенный источник", host="test.example"), next_cursor="continued")
    async with database() as session:
        rows = (await session.scalars(select(TenderMarketPublication).order_by(TenderMarketPublication.id))).all()
        assert [(row.title, row.active) for row in rows] == [(first["title"], True), (second["title"], True)]
        assert (await session.get(TenderMarketCheckpoint, 1)).cursor == "continued"
    assert await put(database, ("continued", 2))
    async with database() as session:
        rows = (await session.scalars(select(TenderMarketPublication).order_by(TenderMarketPublication.id))).all()
        assert [(row.external_id, row.active) for row in rows] == [("1", True), ("2", False)]
        checkpoint = await session.get(TenderMarketCheckpoint, 1)
        assert (checkpoint.cursor, checkpoint.generation) == (None, 3)


@pytest.mark.asyncio
async def test_market_cursor_reset_preserves_last_complete_feed(database, monkeypatch):
    await put(database, (None, 1), notice(1, "Монтаж вентиляции"))
    await put(database, (None, 2), notice(2, "Ремонт кондиционеров"), next_cursor="last-profile")

    async def obsolete_cursor(cursor):
        assert cursor == "last-profile"
        request = httpx.Request("GET", "https://publisher.example/publications")
        httpx.Response(400, request=request).raise_for_status()

    monkeypatch.setattr(tender_market_sync_service, "async_session_maker", database)
    monkeypatch.setattr(tender_market_sync_service, "_pull_page", obsolete_cursor)
    await TenderMarketSyncService.run_scheduled_sync()
    async with database() as session:
        assert len((await session.scalars(select(TenderMarketPublication).where(TenderMarketPublication.active))).all()) == 2
        checkpoint = await session.get(TenderMarketCheckpoint, 1)
        assert (checkpoint.cursor, checkpoint.generation) == (None, 3)


@pytest.mark.asyncio
async def test_companies_find_independent_lots_and_reject_stale_pages(database):
    climate = TenderSearchProfile(
        name="Кондиционеры с монтажом", mode="strict",
        included_directions=["air_conditioning"], activity_combinations=[["supply", "installation"]],
        included_places=[TenderPlace(region="2")],
        excluded_places=[TenderPlace(region="2", locality="Лепель")],
    )
    ventilation = TenderSearchProfile(name="Вентиляция", included_directions=["ventilation"])
    async with database.begin() as session:
        for company_id, profile in ((11, climate), (12, ventilation)):
            session.add(TenantTenderModule(tenant_id=company_id, entitled=True, enabled=True, version=2,
                                           profiles=[profile.model_dump(mode="json")]))
    title = "Поставка кондиционеров с монтажом"
    await put(database, (None, 1),
              notice(1, title),
              notice(2, title, place="Витебская область, г. Лепель"),
              notice(3, "Монтаж вентиляции"),
              notice(4, "Закупка кондиционеров", lots=[
                  {"number": "1", "name": "Поставка кондиционеров", "delivery_place": "г. Витебск"},
                  {"number": "2", "name": "Монтаж кондиционеров", "delivery_place": "г. Витебск"},
              ]),
              notice(5, title, active=False),
              {**notice(6, title), "source": "gias_by", "url": "https://gias.by/gias/#/purchase/current/6"})

    async def list_results(company, *, desired="match", profile=None, before_id=None, version=None, limit=30):
        async with database() as session:
            return await TenderMarketService.list(
                session, TenantScope(tenant_id=company, storefront_id=company), desired=desired,
                profile_name=profile, before_id=before_id, settings_version=version, limit=limit,
            )

    first = await list_results(11, limit=1)
    assert first.profile_names == [climate.name] and first.last_sync_at is not None
    assert [row.source_url.rsplit("/", 1)[-1] for row in first.items] == ["6"]
    assert first.items[0].source == "gias_by"
    assert first.next_before_id == first.items[0].id
    second = await list_results(11, before_id=first.next_before_id, version=first.settings_version)
    assert [row.source_url.rsplit("/", 1)[-1] for row in second.items] == ["1"]
    assert second.next_before_id is None
    other = await list_results(12)
    assert other.profile_names == [ventilation.name]
    assert [row.title for row in other.items] == ["Монтаж вентиляции"]
    under_review = await list_results(11, desired="review")
    assert "Закупка кондиционеров" in {row.title for row in under_review.items}
    assert all(row.source_url.rsplit("/", 1)[-1] != "2" for row in under_review.items)
    with pytest.raises(TenderModuleError) as missing:
        await list_results(12, profile=climate.name)
    assert missing.value.status_code == 404
    with pytest.raises(TenderModuleError) as denied:
        await list_results(13)
    assert denied.value.status_code == 403
    async with database.begin() as session:
        config = await session.get(TenantTenderModule, 11)
        config.version += 1
    with pytest.raises(TenderModuleError) as stale:
        await list_results(11, before_id=first.next_before_id, version=first.settings_version)
    assert stale.value.status_code == 409


async def enable_evidence_for_two_companies(database, monkeypatch):
    monkeypatch.setattr(verification, "async_session_maker", database)
    monkeypatch.setattr(verification.TenderMarketSyncService, "enabled", lambda: True)
    async with database.begin() as session:
        for company_id in (11, 12):
            session.add(TenantTenderModule(tenant_id=company_id, entitled=True, enabled=True, version=2,
                                           profiles=[TenderSearchProfile(name="HVAC").model_dump(mode="json")]))


@pytest.mark.asyncio
async def test_public_originals_resume_and_share_a_literal_report_without_new_provider_calls(database, monkeypatch):
    await enable_evidence_for_two_companies(database, monkeypatch)
    original_url = "https://goszakupki.by/single-source/view/3876716"
    gias_url = "https://gias.by/gias/#/purchase/current/699"
    revision = datetime(2026, 11, 26, tzinfo=timezone.utc)
    publication = dict(notice(699, "Перенос кондиционера", at=revision),
                       source="gias_by", url=gias_url, canonical_url=original_url)
    assert await put(database, (None, 1), publication)

    work = "Демонтаж и установка существующей сплит-системы."
    canonical_external_id = "3876716"
    requests = []

    async def fetch(source, external_id, document_id=None, *, max_bytes=None, market=False):
        assert market
        requests.append((source, external_id, document_id))
        if document_id:
            assert (source, external_id) == ("goszakupki_by", canonical_external_id)
            assert max_bytes == tender_document_reader.MAX_ORIGINAL_BYTES
            return httpx.Response(200, content=b"%PDF-actual-public-market-test")
        is_mirror = (source, external_id) == ("goszakupki_by", canonical_external_id)
        return httpx.Response(200, json={
            "source": source, "external_id": external_id, "source_url": original_url if is_mirror else gias_url,
            "documents": [{"id": "1", "name": "ТЗ.pdf"}] if is_mirror else [],
            "document_inventory_complete": True,
        })

    async def parse(content, kind):
        assert content.startswith(b"%PDF-") and kind == "pdf"
        return {"status": "complete", "total_chars": len(work), "fragments": [
            {"method": "embedded", "page": 2, "fragment": 1, "offset": 0, "text": work},
        ]}

    provider = AsyncMock(return_value=([{"kind": "work_scope", "fragment": 0, "quote": work}], "fixture"))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_fetch", fetch)
    monkeypatch.setattr(tender_document_reader, "_extract_in_worker", parse)
    monkeypatch.setattr(tender_qualification, "_request_candidates", provider)

    async def access(company, *, request=False):
        async with database() as session:
            lookup = Evidence.request if request else Evidence.get
            return await lookup(session, TenantScope(tenant_id=company, storefront_id=42), 1)

    assert (await access(11, request=True)).status == "queued"
    assert (await access(12, request=True)).status == "queued"
    await Evidence.run_one()
    receipt = await access(11)
    assert receipt.status == "completed" and receipt.report.document_coverage_complete
    assert receipt.documents_source_url == original_url
    assert any(fact.evidence.quote == work and fact.evidence.location.startswith("стр. 2")
               for fact in receipt.report.findings)
    assert await access(12, request=True) == receipt
    assert requests == [("gias_by", "699", None), ("goszakupki_by", canonical_external_id, None),
                        ("goszakupki_by", canonical_external_id, "1")]
    provider.assert_awaited_once()
    with pytest.raises(TenderModuleError) as denied:
        await access(13)
    assert denied.value.status_code == 403

    async with database.begin() as session:
        config = await session.get(TenantTenderModule, 11)
        config.entitled = config.enabled = False
    with pytest.raises(TenderModuleError) as revoked:
        await access(11)
    assert revoked.value.status_code == 403

    assert await put(database, (None, 2), {**publication, "updated_at": revision + timedelta(hours=1)})
    assert (await access(12)).status == "unrequested"
    await access(12, request=True)
    await Evidence.run_one()
    assert (await access(12)).report == receipt.report
    provider.assert_awaited_once()
    assert len(requests) == 6


@pytest.mark.asyncio
async def test_worker_reclaims_an_interrupted_read_and_fences_the_old_lease(database, monkeypatch):
    await enable_evidence_for_two_companies(database, monkeypatch)
    await put(database, (None, 1), notice(1, "Монтаж вентиляции"))
    scope = TenantScope(tenant_id=11, storefront_id=42)
    async with database() as session:
        await Evidence.request(session, scope, 1)
    first = await Evidence._claim()
    assert first and await Evidence._claim() is None
    async with database.begin() as session:
        row = await session.get(TenderMarketEvidence, 1)
        row.lease_until = datetime.now(timezone.utc) - timedelta(seconds=1)
    replacement = await Evidence._claim()
    assert replacement and replacement.token != first.token
    await Evidence._settle(first, None)
    async with database() as session:
        assert (await Evidence.get(session, scope, 1)).status == "reading"
    await Evidence._settle(replacement, None)
    async with database() as session:
        failed = await Evidence.get(session, scope, 1)
        assert failed.status == "failed" and failed.error and not failed.report
    assert await Evidence._claim() is None


@pytest.mark.asyncio
async def test_market_deduplicates_only_verified_canonical_publications(database):
    real = notice(3876716, "Перенос кондиционера")
    gias = dict(notice(699, real["title"]), source="gias_by",
                url="https://gias.by/gias/#/purchase/current/699", canonical_url=real["url"])
    independent = dict(gias, external_id="698", url="https://gias.by/gias/#/purchase/current/698", canonical_url=None)
    await put(database, (None, 1), real, gias, independent)
    async with database.begin() as session:
        session.add(TenantTenderModule(tenant_id=11, entitled=True, enabled=True, version=2,
                                       profiles=[TenderSearchProfile(name="Все HVAC").model_dump(mode="json")]))
    async with database() as session:
        result = await TenderMarketService.list(
            session, TenantScope(tenant_id=11, storefront_id=42), desired="match", profile_name=None,
            before_id=None, settings_version=None, limit=20,
        )
    assert [item.source_url for item in result.items] == [independent["url"], real["url"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("original_source,original_url", [
    ("goszakupki_by", "https://goszakupki.by/marketing/view/3880632"),
    ("butb_by", "https://zakupki.butb.by/auctions/viewinvitation.html?auction=RQ20261125402772"),
])
async def test_market_prefers_native_publication_over_linked_icetrade(database, original_source, original_url):
    original = dict(notice(1, "Поставка кондиционеров"), source=original_source, url=original_url)
    mirror = dict(
        original, source="icetrade_by", external_id="2", url="https://icetrade.by/tenders/all/view/2",
        canonical_url=original_url,
    )
    independent = dict(
        mirror, external_id="3", url="https://icetrade.by/tenders/all/view/3",
        canonical_url="https://icetrade.by/tenders/all/view/2",
    )
    await put(database, (None, 1), original, dict(mirror, canonical_url=None), independent)
    # A normal resync must apply the newly recognized reference even when the
    # upstream publication timestamp did not change.
    await put(database, (None, 2), original, mirror, independent)
    async with database.begin() as session:
        session.add(TenantTenderModule(
            tenant_id=11, entitled=True, enabled=True, version=2,
            profiles=[TenderSearchProfile(name="Все HVAC").model_dump(mode="json")],
        ))
    scope = TenantScope(tenant_id=11, storefront_id=42)

    async def visible_urls():
        async with database() as session:
            result = await TenderMarketService.list(
                session, scope, desired="match", profile_name=None, before_id=None,
                settings_version=None, limit=20,
            )
            return [item.source_url for item in result.items]

    assert await visible_urls() == [independent["url"], original_url]
    await put(database, (None, 3), mirror, independent)
    assert await visible_urls() == [independent["url"], mirror["url"]]


@pytest.mark.asyncio
@pytest.mark.parametrize("mismatch", [None, "deadline", "title", "older_mirror", "previous_sweep"])
async def test_market_filters_original_using_current_mirror_lots(database, mismatch):
    at = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    deadline = at + timedelta(days=1)
    original = {**notice(3876716, "Монтаж кондиционера", at=at, lots=[]), "deadline_at": deadline}
    mirror = {
        **notice(699, original["title"], at=at, place="Витебская область, г. Лепель"),
        "source": "gias_by",
        "url": "https://gias.by/gias/#/purchase/current/699",
        "canonical_url": original["url"],
        "deadline_at": deadline + timedelta(seconds=59),
    }
    if mismatch == "deadline":
        mirror["deadline_at"] += timedelta(days=1)
    elif mismatch == "title":
        mirror["title"] = "Монтаж вентиляции"
    elif mismatch == "older_mirror":
        mirror["updated_at"] -= timedelta(hours=1)
    await put(database, (None, 1), original, mirror)
    if mismatch == "previous_sweep":
        await put(database, (None, 2), original, next_cursor="mirror-pending")
    without_lepel = TenderSearchProfile(
        name="Без Лепеля", excluded_places=[TenderPlace(region="2", locality="Лепель")],
    )
    lepel = TenderSearchProfile(
        name="Монтаж в Лепеле", mode="strict", included_places=[TenderPlace(region="2", locality="Лепель")],
        activity_combinations=[["installation"]],
    )
    async with database.begin() as session:
        for company_id, profile in ((11, without_lepel), (12, lepel)):
            session.add(TenantTenderModule(
                tenant_id=company_id, entitled=True, enabled=True, profiles=[profile.model_dump(mode="json")],
            ))

    async with database() as session:
        publication_id = await session.scalar(select(TenderMarketPublication.id).where(
            TenderMarketPublication.source == "goszakupki_by",
        ))
        excluded_scope = TenantScope(tenant_id=11, storefront_id=42)
        allowed_scope = TenantScope(tenant_id=12, storefront_id=43)
        excluded = await TenderMarketService.list(
            session, excluded_scope, desired="review", profile_name=None,
            before_id=None, settings_version=None, limit=20,
        )
        included = await TenderMarketService.list(
            session, allowed_scope, desired="match", profile_name=None,
            before_id=None, settings_version=None, limit=20,
        )
        if mismatch is None:
            assert not excluded.items
            (result,) = included.items
            assert result.id == publication_id and result.source_url == original["url"]
            assert result.profiles[0].lots[0].lot_key == "1"
            with pytest.raises(TenderModuleError) as rejected:
                await Evidence.get(session, excluded_scope, publication_id)
            assert rejected.value.status_code == 404
            assert (await Evidence.get(session, allowed_scope, publication_id)).status == "unrequested"
        else:
            assert not included.items
            (result,) = excluded.items
            assert result.source_url == original["url"]
            assert result.profiles[0].result.reason == "unconfirmed_place"


@pytest.mark.asyncio
async def test_market_reads_delegated_inventory_with_the_scoped_gias_identity(monkeypatch):
    publication = TenderMarketPublication(
        source="gias_by", external_id="699", source_url="https://gias.by/gias/#/purchase/current/699",
        canonical_url="https://goszakupki.by/single-source/view/3876716",
    )
    body = {
        "source": publication.source, "external_id": publication.external_id, "source_url": publication.source_url,
        "documents_source_url": publication.canonical_url, "documents": [{"id": "doc", "name": "ТЗ.pdf"}],
    }
    fetch = AsyncMock(return_value=httpx.Response(200, json=body))
    monkeypatch.setattr(BelzakupkiEnrichmentService, "_fetch", fetch)
    result = await market_original_inventory(publication)
    assert result.document_identity == ("gias_by", "699") and result.documents_source_url == publication.canonical_url
    fetch.assert_awaited_once_with("gias_by", "699", market=True)
    fetch.return_value = httpx.Response(200, json={**body, "documents_source_url": "https://goszakupki.by/request/view/888"})
    with pytest.raises(ValueError, match="inventory reference"):
        await market_original_inventory(publication)
