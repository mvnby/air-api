from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlmodel import SQLModel, select

from models import Tenant, TenantTenderModule, TenderMarketCheckpoint, TenderMarketPublication
from models.tenancy import TenantScope
from schemas_tender_market import MarketPageInput
from schemas_tender_search import TenderPlace, TenderSearchProfile
from services import tender_market_sync_service
from services.tender_market_service import TenderMarketService
from services.tender_market_sync_service import TenderMarketSyncService
from services.tender_module_service import TenderModuleError


@pytest_asyncio.fixture
async def database():
    engine = create_async_engine("sqlite+aiosqlite://")
    async with engine.begin() as connection:
        await connection.run_sync(lambda db: SQLModel.metadata.create_all(db, tables=[
            Tenant.__table__, TenantTenderModule.__table__,
            TenderMarketCheckpoint.__table__, TenderMarketPublication.__table__,
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
    import httpx

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
              notice(6, title))

    async def list_results(company, *, desired="match", profile=None, before_id=None, version=None, limit=30):
        async with database() as session:
            return await TenderMarketService.list(
                session, TenantScope(tenant_id=company, storefront_id=company), desired=desired,
                profile_name=profile, before_id=before_id, settings_version=version, limit=limit,
            )

    first = await list_results(11, limit=1)
    assert first.profile_names == [climate.name] and first.last_sync_at is not None
    assert [row.source_url.rsplit("/", 1)[-1] for row in first.items] == ["6"]
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
