"""Durable snapshots exercised against a real file DB, without external HTTP."""
import asyncio
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from crud import dashboard_analytics as store
from models.analytics_connection import AnalyticsConnection
from models.dashboard_analytics import DashboardAnalyticsSnapshot as Snapshot
from models.tenancy import TenantScope
from services import dashboard_analytics_snapshots as snapshots
from services.dashboard_analytics_worker import DashboardAnalyticsWorker
from services.dashboard_overview_service import DashboardOverviewService

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)
START, END = date(2026, 10, 1), date(2026, 10, 24)
SCOPE = TenantScope(2, 7)


@pytest.fixture
async def repository(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'snapshots.db'}")
    async with engine.begin() as connection:
        await connection.execute(text("PRAGMA foreign_keys=ON"))
        await connection.execute(text("CREATE TABLE tenant (id INTEGER PRIMARY KEY, status TEXT, is_system BOOLEAN, demo_read_only BOOLEAN)"))
        await connection.execute(text("CREATE TABLE storefront (id INTEGER PRIMARY KEY, tenant_id INTEGER NOT NULL, status TEXT, UNIQUE(id,tenant_id))"))
        await connection.execute(text("INSERT INTO tenant VALUES (1,'active',1,0),(2,'active',0,0),(3,'active',0,0),(4,'active',0,1),(5,'disabled',0,0)"))
        await connection.execute(text("INSERT INTO storefront VALUES (1,1,'active'),(7,2,'active'),(8,2,'active'),(9,3,'active'),(10,4,'active'),(11,5,'active'),(12,2,'disabled')"))
        await connection.run_sync(lambda conn: AnalyticsConnection.__table__.create(conn))
        await connection.run_sync(lambda conn: Snapshot.__table__.create(conn))
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()


async def add_source(factory, provider="yandex_metrika", scope=SCOPE):
    async with factory() as session:
        connection = AnalyticsConnection(
            tenant_id=scope.tenant_id, storefront_id=scope.storefront_id,
            provider=provider, encrypted_credentials="never-decrypt-in-reader",
            credentials_fingerprint="token-v1", public_config={"counter_id": "123"},
        )
        session.add(connection)
        await session.commit()
        return snapshots.SourceConfiguration(provider, snapshots.revision(connection))


def marketing(provider="yandex_metrika", visits=123, **kwargs):
    return {"marketing": {"status": "fresh", "visits": visits, "sources": [],
        "providers": [{"provider": provider, "status": "fresh", "visits": visits}], **kwargs}}


async def save(factory, config, *, scope=SCOPE, start=START, end=END, now=NOW, payload=None):
    values = snapshots.key_values(scope, config, start, end)
    async with factory() as session:
        token = await store.claim(session, values=values, now=now)
        assert token
        assert await store.finish(session, key=values["key"], token=token, now=now,
                                  payload=payload or marketing(config.provider), ttl_seconds=snapshots.ttl(config.provider))
    return values


async def read(factory, *, scope=SCOPE, start=START, end=END, providers=("yandex_metrika",), now=NOW):
    async with factory() as session:
        return await snapshots.read_sources(session, scope, providers, start, end, now)


@pytest.mark.asyncio
async def test_success_is_persistent_across_sessions_and_fresh_reader_instances(repository):
    config = await add_source(repository)
    await save(repository, config, payload=marketing(visits=451, bounce_rate=23.1, average_session_duration_seconds=48.2))
    # No in-process provider cache, object or session from the write is reused.
    async with repository() as session:
        result = await snapshots.SavedMarketingProvider().get_snapshot(
            session=session, tenant_scope=SCOPE, start=START, end_exclusive=END)
    assert result.visits == 451
    assert result.bounce_rate == 23.1
    assert result.average_session_duration_seconds == 48.2
    assert result.providers[0].period_end == END
    assert snapshots.utc(result.providers[0].updated_at) == NOW


@pytest.mark.asyncio
async def test_failure_preserves_success_and_exponential_backoff_blocks_repeated_attempts(repository):
    config = await add_source(repository)
    values = await save(repository, config, payload=marketing(visits=321))
    now = NOW + timedelta(hours=1)
    async with repository() as session:
        for failure in range(1, 9):
            token = await store.claim(session, values=values, now=now)
            assert token
            assert await store.finish(session, key=values["key"], token=token, now=now, error_code="provider_unavailable")
            row = (await store.exact_rows(session, [values["key"]]))[values["key"]]
            delay = min(3600, 60 * 2 ** min(failure - 1, 6))
            assert row.failure_count == failure
            assert row.payload["marketing"]["visits"] == 321
            assert snapshots.utc(row.last_success_at) == NOW
            assert snapshots.utc(row.last_attempt_at) == now
            assert snapshots.utc(row.next_retry_at) == now + timedelta(seconds=delay)
            assert await store.claim(session, values=values, now=now + timedelta(seconds=delay - 1)) is None
            now += timedelta(seconds=delay)
    [(state, payload)] = await read(repository, now=now)
    assert state["status"] == "stale" and state["error_code"] == "provider_unavailable"
    assert payload["marketing"]["visits"] == 321
    async with repository() as session:
        token = await store.claim(session, values=values, now=now)
        await store.finish(session, key=values["key"], token=token, now=now, payload=marketing(visits=999))
    [(state, payload)] = await read(repository, now=now)
    assert state["status"] == "fresh" and state["error_code"] is None
    assert payload["marketing"]["visits"] == 999


@pytest.mark.asyncio
async def test_partial_source_failure_does_not_erase_other_source(repository):
    metrika = await add_source(repository)
    direct = await add_source(repository, "yandex_direct")
    await save(repository, metrika, now=NOW + timedelta(hours=1), payload=marketing(visits=888))
    direct_values = await save(repository, direct, payload=marketing("yandex_direct", visits=None, ad_spend=120, clicks=20, impressions=200, platform_conversions=3, currency="BYN"))
    async with repository() as session:
        token = await store.claim(session, values=direct_values, now=NOW + timedelta(hours=1))
        await store.finish(session, key=direct_values["key"], token=token, now=NOW + timedelta(hours=1), error_code="provider_unavailable")
    states = await read(repository, providers=("yandex_metrika", "yandex_direct"), now=NOW + timedelta(hours=1, seconds=1))
    assert [state["status"] for state, _ in states] == ["fresh", "stale"]
    assert states[0][1]["marketing"]["visits"] == 888
    assert states[1][1]["marketing"]["ad_spend"] == 120


@pytest.mark.asyncio
async def test_expired_lease_can_be_reclaimed_and_old_worker_is_fenced(repository):
    config = await add_source(repository)
    values = snapshots.key_values(SCOPE, config, START, END)
    async with repository() as first, repository() as second:
        old = await store.claim(first, values=values, now=NOW, lease_seconds=90)
        assert old
        assert await store.claim(second, values=values, now=NOW + timedelta(seconds=89)) is None
        new = await store.claim(second, values=values, now=NOW + timedelta(seconds=91))
        assert new and new != old
        assert not await store.finish(first, key=values["key"], token=old, now=NOW + timedelta(seconds=92), payload=marketing(visits=1))
        assert await store.finish(second, key=values["key"], token=new, now=NOW + timedelta(seconds=93), payload=marketing(visits=2))
    [(state, payload)] = await read(repository, now=NOW + timedelta(seconds=94))
    assert payload["marketing"]["visits"] == 2


@pytest.mark.asyncio
async def test_midnight_fallback_keeps_actual_period_and_never_crosses_month(repository):
    config = await add_source(repository)
    await save(repository, config)
    day_after = END + timedelta(days=1)
    [(state, payload)] = await read(repository, end=day_after, now=NOW + timedelta(days=1))
    assert state["status"] == "stale"
    assert state["period_start"] == START and state["period_end"] == END
    assert payload["marketing"]["visits"] == 123
    [(state, payload)] = await read(repository, start=date(2026, 11, 1), end=date(2026, 11, 2), now=NOW + timedelta(days=10))
    assert state["status"] == "pending" and payload is None
    assert state["period_start"] == date(2026, 11, 1)


@pytest.mark.asyncio
async def test_old_success_survives_first_failure_after_midnight(repository):
    config = await add_source(repository)
    await save(repository, config)
    next_values = snapshots.key_values(SCOPE, config, START, END + timedelta(days=1))
    async with repository() as session:
        token = await store.claim(session, values=next_values, now=NOW + timedelta(days=1))
        await store.finish(session, key=next_values["key"], token=token, now=NOW + timedelta(days=1), error_code="timeout")
    [(state, payload)] = await read(repository, end=END + timedelta(days=1), now=NOW + timedelta(days=1))
    assert state["status"] == "stale" and state["error_code"] == "timeout"
    assert state["period_end"] == END and payload["marketing"]["visits"] == 123


@pytest.mark.asyncio
async def test_config_change_invalidates_but_oauth_rotation_preserves_revision(repository):
    config = await add_source(repository)
    await save(repository, config)
    async with repository() as session:
        row = (await store.connection_rows(session, SCOPE))[0]
        row.credentials_fingerprint = "rotated-token-fingerprint"
        row.encrypted_credentials = "rotated-ciphertext"
        session.add(row)
        await session.commit()
    assert (await read(repository))[0][0]["status"] == "fresh"
    async with repository() as session:
        row = (await store.connection_rows(session, SCOPE))[0]
        row.public_config = {"counter_id": "999"}
        session.add(row)
        await session.commit()
    [(state, payload)] = await read(repository)
    assert state["status"] == "pending" and payload is None


@pytest.mark.asyncio
async def test_reader_is_exact_tenant_storefront_and_configuration_scope(repository):
    config = await add_source(repository)
    await save(repository, config, payload=marketing(visits=111))
    for scope in (TenantScope(2, 8), TenantScope(3, 9)):
        other = await add_source(repository, scope=scope)
        # A valid source exists, but no snapshot from 2:7 may be reused.
        [(state, payload)] = await read(repository, scope=scope)
        assert state["status"] == "pending" and payload is None
        assert snapshots.key_values(scope, other, START, END)["key"] != snapshots.key_values(SCOPE, config, START, END)["key"]


@pytest.mark.asyncio
async def test_cold_overview_returns_live_canonical_crm_without_waiting_for_provider(repository, monkeypatch):
    from services import dashboard_analytics_sources
    await add_source(repository)
    external = AsyncMock(side_effect=AssertionError("GET must never call external refresh"))
    monkeypatch.setattr(dashboard_analytics_sources, "fetch_source", external)
    service = DashboardOverviewService()
    service._revenue = AsyncMock(side_effect=[(4321, {}), (4000, {})])
    service._lead_count = AsyncMock(side_effect=[4, 2])
    service._sales = AsyncMock(side_effect=[(8, {}, 2.0), (5, {}, 1.0)])
    service._installations = AsyncMock(side_effect=[(3, 2.0), (2, 1.0)])
    service._touchpoints = AsyncMock(return_value=5)
    service._receivables = AsyncMock(return_value=777)
    service._measurements = AsyncMock(side_effect=[(4, 1.0), (3, 1.0)])
    service._proposals = AsyncMock(side_effect=[(7, 1.0), (5, 1.0)])
    service._acquired_customers = AsyncMock(return_value=3)
    async with repository() as session:
        result = await asyncio.wait_for(service.get_overview(session, tenant_scope=SCOPE, now=NOW), timeout=1)
    assert result.kpis.revenue.current == 4321
    assert result.kpis.sales.current == 8
    assert result.kpis.receivables.current == 777
    assert result.marketing.status == "pending" and result.marketing.visits is None
    external.assert_not_awaited()


@pytest.mark.asyncio
async def test_discovery_does_not_decrypt_credentials_and_filters_disabled_demo_scope(repository, monkeypatch):
    from services.analytics_connection_service import AnalyticsCredentialCipher
    await add_source(repository)
    monkeypatch.setattr(AnalyticsCredentialCipher, "decrypt", lambda *a, **k: pytest.fail("Reader decrypted credentials"))
    async with repository() as session:
        assert len(await snapshots.configurations(session, SCOPE)) == 1
        scopes = await store.active_scopes(session)
    assert {(s.tenant_id, s.storefront_id) for s in scopes} == {(1, 1), (2, 7), (2, 8), (3, 9)}


@pytest.mark.asyncio
async def test_worker_owns_separate_sessions_and_never_exceeds_two_fetches(repository):
    await add_source(repository)
    await add_source(repository, "yandex_direct")
    active, maximum = set(), 0
    session_ids, closed = set(), set()
    retained_sessions = []
    entered = asyncio.Event()
    release = asyncio.Event()
    @asynccontextmanager
    async def tracked_factory():
        async with repository() as session:
            retained_sessions.append(session)
            session_ids.add(id(session))
            try:
                yield session
            finally:
                closed.add(id(session))
    async def fetch(session, scope, provider, start, end):
        nonlocal maximum
        assert id(session) not in active
        active.add(id(session))
        maximum = max(maximum, len(active))
        if len(active) == 2:
            entered.set()
        await release.wait()
        active.remove(id(session))
        return marketing(provider)
    worker = DashboardAnalyticsWorker(session_factory=tracked_factory, fetch_source=fetch, clock=lambda: NOW)
    task = asyncio.create_task(worker.run_once())
    try:
        await asyncio.wait_for(entered.wait(), timeout=2)
        assert maximum == 2
        release.set()
        assert await asyncio.wait_for(task, timeout=2) == 4
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
    assert len(session_ids) == 5  # discovery plus one session per source/window
    assert closed == session_ids and not active
    # Same persisted keys are not refreshed again by another worker/process.
    second_fetch = AsyncMock()
    assert await DashboardAnalyticsWorker(session_factory=repository, fetch_source=second_fetch, clock=lambda: NOW).run_once() == 0
    second_fetch.assert_not_awaited()


@pytest.mark.asyncio
async def test_worker_cancellation_closes_sessions_and_stops_fetch(repository):
    await add_source(repository, "yandex_webmaster")
    started, cancelled = asyncio.Event(), asyncio.Event()
    closed = []
    @asynccontextmanager
    async def tracked_factory():
        async with repository() as session:
            try:
                yield session
            finally:
                closed.append(session)
    async def hang(*args):
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
    worker = DashboardAnalyticsWorker(session_factory=tracked_factory, fetch_source=hang, clock=lambda: NOW)
    task = asyncio.create_task(worker.run_once())
    await asyncio.wait_for(started.wait(), timeout=2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    assert cancelled.is_set() and len(closed) == 2
    async with repository() as session:
        rows = (await session.execute(select(Snapshot))).scalars().all()
    assert len(rows) == 1 and rows[0].last_success_at is None
    assert rows[0].lease_token  # a new owner can recover after lease expiry


@pytest.mark.asyncio
async def test_worker_discards_report_if_configuration_changes_during_http(repository):
    config = await add_source(repository, "yandex_webmaster")
    async def fetch(session, scope, provider, start, end):
        async with repository() as editor:
            connection = (await store.connection_rows(editor, scope))[0]
            connection.public_config = {"host_id": "new-host"}
            editor.add(connection)
            await editor.commit()
        return {"search": {"status": "fresh", "queries": []}}
    worker = DashboardAnalyticsWorker(session_factory=repository, fetch_source=fetch, clock=lambda: NOW)
    await worker.run_once()
    async with repository() as session:
        rows = (await session.execute(select(Snapshot))).scalars().all()
    assert len(rows) == 1
    assert rows[0].payload is None and rows[0].error_code == "source_changed"
    assert (await read(repository, providers=("yandex_webmaster",)))[0][0]["status"] == "pending"


@pytest.mark.asyncio
async def test_worker_uses_task_time_for_queued_claims_and_success_time_for_ttl(repository):
    await add_source(repository)
    times = [NOW]
    observed = []
    async def fetch(session, scope, provider, start, end):
        observed.append(times[0])
        times[0] += timedelta(seconds=10)
        return marketing(provider)
    worker = DashboardAnalyticsWorker(session_factory=repository, fetch_source=fetch, concurrency=1, clock=lambda: times[0])
    assert await worker.run_once() == 2
    async with repository() as session:
        rows = sorted((await session.execute(select(Snapshot))).scalars().all(), key=lambda row: snapshots.utc(row.last_attempt_at))
    assert [snapshots.utc(r.last_attempt_at) for r in rows] == [NOW, NOW + timedelta(seconds=10)]
    assert [snapshots.utc(r.last_success_at) for r in rows] == [NOW + timedelta(seconds=10), NOW + timedelta(seconds=20)]
    assert all(snapshots.utc(r.next_retry_at) == snapshots.utc(r.last_success_at) + timedelta(hours=1) for r in rows)


@pytest.mark.asyncio
async def test_get_reads_snapshot_while_background_provider_hangs_without_holding_db_write_lock(repository):
    await add_source(repository, "yandex_webmaster")
    started = asyncio.Event()
    async def hang(*args):
        started.set()
        await asyncio.Event().wait()
    worker = DashboardAnalyticsWorker(session_factory=repository, fetch_source=hang, clock=lambda: NOW)
    task = asyncio.create_task(worker.run_once())
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        async with repository() as session:
            result = await asyncio.wait_for(snapshots.SavedSearchDemandProvider().get_snapshot(
                session=session, tenant_scope=SCOPE, start=START, end_exclusive=END), timeout=.5)
        assert result.status == "pending" and not result.queries
        assert not task.done()
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


@pytest.mark.asyncio
async def test_search_snapshot_uses_three_hour_ttl_and_keeps_actual_provider_period(repository):
    config = await add_source(repository, "google_search_console")
    report = {"search": {"queries": [{"provider": config.provider, "query": "air conditioner", "clicks": 5, "impressions": 100, "ctr": 5.0, "avg_position": 3.2}]}}
    await save(repository, config, payload=report)
    providers = ("google_search_console",)
    assert (await read(repository, providers=providers, now=NOW + timedelta(hours=2, minutes=59)))[0][0]["status"] == "fresh"
    assert (await read(repository, providers=providers, now=NOW + timedelta(hours=3)))[0][0]["status"] == "stale"
    async with repository() as session:
        result = await snapshots.SavedSearchDemandProvider().get_snapshot(
            session=session, tenant_scope=SCOPE, start=START, end_exclusive=END)
    provider = next(p for p in result.providers if p.provider == config.provider)
    assert provider.period_start == START and provider.period_end == END
    assert result.queries[0].query == "air conditioner"


@pytest.mark.asyncio
async def test_reader_excludes_incompatible_schema_and_returns_bounded_history(repository):
    config = await add_source(repository)
    for offset in range(5):
        await save(repository, config, end=END - timedelta(days=offset), payload=marketing(visits=100 + offset))
    # More recent but incompatible calculation must not replace supported data.
    incompatible = snapshots.key_values(SCOPE, config, START, END + timedelta(days=1))
    incompatible.update(key="a" * 64, schema_version=999)
    async with repository() as session:
        token = await store.claim(session, values=incompatible, now=NOW)
        await store.finish(session, key=incompatible["key"], token=token, now=NOW, payload=marketing(visits=999))
        candidates = await store.read_candidates(session, tenant_id=SCOPE.tenant_id, storefront_id=SCOPE.storefront_id,
            configurations=[config], periods=[(START, END + timedelta(days=1))])
    assert len(candidates) <= 2
    assert all(row.schema_version == 1 for row in candidates)
    assert max(row.period_end for row in candidates) == END


@pytest.mark.asyncio
async def test_existing_oauth_persistence_does_not_rotate_snapshot_configuration_revision(repository, monkeypatch):
    from services.analytics_connection_service import AnalyticsConnectionService, AnalyticsCredentialCipher
    config = await add_source(repository, "google_analytics")
    await save(repository, config, payload=marketing("google_analytics", visits=14))
    monkeypatch.setattr(AnalyticsCredentialCipher, "encrypt", lambda *a, **k: "new-encrypted-token")
    async with repository() as session:
        await AnalyticsConnectionService.persist_refreshed_credentials(
            session, tenant_scope=SCOPE, provider="google_analytics", credentials={"access_token": "refreshed"})
        current = (await snapshots.configurations(session, SCOPE))[0]
    assert current == config
    [(state, payload)] = await read(repository, providers=("google_analytics",))
    assert state["status"] == "fresh" and payload["marketing"]["visits"] == 14


@pytest.mark.asyncio
async def test_worker_batch_limit_and_no_configurations_produce_bounded_or_zero_io(repository):
    empty = AsyncMock()
    assert await DashboardAnalyticsWorker(session_factory=repository, fetch_source=empty, clock=lambda: NOW).run_once() == 0
    empty.assert_not_awaited()
    await add_source(repository)
    await add_source(repository, "google_ads")
    fetch = AsyncMock(side_effect=lambda session, scope, provider, start, end: marketing(provider))
    worker = DashboardAnalyticsWorker(session_factory=repository, fetch_source=fetch, batch_limit=1, clock=lambda: NOW)
    assert await worker.run_once() == 1
    assert fetch.await_count == 1
    async with repository() as session:
        rows = (await session.execute(select(Snapshot))).scalars().all()
    assert len(rows) == 1


@pytest.mark.asyncio
async def test_worker_partial_failure_preserves_old_success_and_other_provider_refreshes(repository):
    metrika = await add_source(repository)
    await add_source(repository, "yandex_direct")
    old_values = await save(repository, metrika, payload=marketing(visits=876))
    now = NOW + timedelta(hours=1)
    async def fetch(session, scope, provider, start, end):
        if provider == "yandex_metrika":
            raise RuntimeError("upstream failure with credential must stay private")
        return marketing(provider, visits=None, ad_spend=44, currency="BYN")
    worker = DashboardAnalyticsWorker(session_factory=repository, fetch_source=fetch, clock=lambda: now)
    assert await worker.run_once() == 4
    results = await read(repository, providers=("yandex_metrika", "yandex_direct"), now=now)
    assert results[0][0]["status"] == "stale" and results[0][1]["marketing"]["visits"] == 876
    assert results[1][0]["status"] == "fresh" and results[1][1]["marketing"]["ad_spend"] == 44
    async with repository() as session:
        old = (await store.exact_rows(session, [old_values["key"]]))[old_values["key"]]
    assert old.failure_count == 1 and old.error_code == "provider_unavailable"
    assert snapshots.utc(old.next_retry_at) == now + timedelta(seconds=60)
    assert snapshots.utc(old.last_success_at) == NOW
    assert await worker.run_once() == 0


@pytest.mark.asyncio
async def test_worker_waits_for_owned_sources_after_another_claim_fails(repository, monkeypatch):
    await add_source(repository, "yandex_webmaster")
    await add_source(repository, "google_search_console")
    started, release = asyncio.Event(), asyncio.Event()
    original_claim = store.claim
    async def claim(session, *, values, **kwargs):
        if values["provider"] == "yandex_webmaster":
            raise RuntimeError("simulated database failure")
        return await original_claim(session, values=values, **kwargs)
    monkeypatch.setattr(store, "claim", claim)
    async def fetch(*args):
        started.set()
        await release.wait()
        return {"search": {"queries": []}}
    worker = DashboardAnalyticsWorker(session_factory=repository, fetch_source=fetch, clock=lambda: NOW)
    task = asyncio.create_task(worker.run_once())
    try:
        await asyncio.wait_for(started.wait(), timeout=2)
        await asyncio.sleep(0)
        assert not task.done(), "The failed key must not orphan another owned refresh"
        release.set()
        assert await asyncio.wait_for(task, timeout=2) == 1
    finally:
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)
