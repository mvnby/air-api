"""PostgreSQL locking and isolation; db_engine owns a physical pytest test DB."""
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker

from crud import dashboard_analytics as store
from models.dashboard_analytics import DashboardAnalyticsSnapshot as Snapshot
from models.tenancy import Storefront, Tenant, TenantScope
from services.dashboard_analytics_snapshots import SourceConfiguration, key_values

NOW = datetime(2026, 10, 23, 12, tzinfo=timezone.utc)


async def setup_scope(factory):
    async with factory() as session:
        tenant = Tenant(slug="snapshot-pg-test", display_name="Snapshot test", status="active")
        session.add(tenant)
        await session.flush()
        storefront = Storefront(tenant_id=tenant.id, slug="snapshot-pg-test", display_name="Snapshot test", status="active")
        session.add(storefront)
        await session.commit()
        return TenantScope(tenant.id, storefront.id)


def values_for(scope):
    return key_values(scope, SourceConfiguration("yandex_metrika", "test-revision"), date(2026, 10, 1), date(2026, 10, 24))


@pytest.mark.asyncio
async def test_concurrent_postgres_workers_claim_exactly_one_source_key(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scope = await setup_scope(factory)
    values = values_for(scope)
    ready, start = 0, asyncio.Event()
    async def compete():
        nonlocal ready
        async with factory() as session:
            ready += 1
            if ready == 6:
                start.set()
            await start.wait()
            return await store.claim(session, values=values, now=NOW)
    tokens = await asyncio.gather(*(compete() for _ in range(6)))
    winners = [token for token in tokens if token]
    assert len(winners) == 1
    async with factory() as session:
        rows = (await session.execute(select(Snapshot))).scalars().all()
    assert len(rows) == 1 and rows[0].lease_token == winners[0]


@pytest.mark.asyncio
async def test_postgres_takeover_fences_late_old_success_and_failure(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    values = values_for(await setup_scope(factory))
    async with factory() as old, factory() as new:
        token_old = await store.claim(old, values=values, now=NOW, lease_seconds=1)
        token_new = await store.claim(new, values=values, now=NOW + timedelta(seconds=2))
        assert token_old and token_new and token_old != token_new
        assert not await store.finish(old, key=values["key"], token=token_old, now=NOW + timedelta(seconds=3), payload={"marketing": {"visits": 999}})
        assert not await store.finish(old, key=values["key"], token=token_old, now=NOW + timedelta(seconds=3), error_code="late_old_error")
        assert await store.finish(new, key=values["key"], token=token_new, now=NOW + timedelta(seconds=4), payload={"marketing": {"visits": 12}})
    async with factory() as restarted:
        row = (await store.exact_rows(restarted, [values["key"]]))[values["key"]]
        assert row.payload == {"marketing": {"visits": 12}}
        assert row.error_code is None and row.lease_token is None


@pytest.mark.asyncio
async def test_postgres_scope_fk_rejects_foreign_tenant_storefront_pair(db_engine):
    factory = async_sessionmaker(db_engine, expire_on_commit=False)
    scope = await setup_scope(factory)
    values = values_for(TenantScope(1, scope.storefront_id))
    async with factory() as session:
        with pytest.raises(IntegrityError):
            await store.claim(session, values=values, now=NOW)
        await session.rollback()
        assert (await session.execute(select(Snapshot))).scalars().all() == []


@pytest.mark.asyncio
async def test_snapshot_migration_round_trip_on_real_postgres_schema(db_engine):
    import importlib.util
    from pathlib import Path
    from alembic.migration import MigrationContext
    from alembic.operations import Operations
    from sqlalchemy import inspect

    path = Path("alembic/versions/dash20261023snap01_dashboard_snapshots.py")
    spec = importlib.util.spec_from_file_location("dashboard_snapshot_pg_migration", path)
    migration = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(migration)
    async with db_engine.connect() as connection:
        transaction = await connection.begin()
        try:
            def exercise(sync_connection):
                migration.op = Operations(MigrationContext.configure(sync_connection))
                migration.downgrade()
                assert "dashboard_analytics_snapshot" not in inspect(sync_connection).get_table_names()
                assert "snapshot_revision" not in {c["name"] for c in inspect(sync_connection).get_columns("analytics_connection")}
                migration.upgrade()
                inspector = inspect(sync_connection)
                columns = {c["name"]: c for c in inspector.get_columns("dashboard_analytics_snapshot")}
                assert columns["last_success_at"]["type"].timezone
                assert columns["last_attempt_at"]["type"].timezone
                assert columns["next_retry_at"]["type"].timezone
                assert columns["lease_until"]["type"].timezone
                assert not columns["configuration_revision"]["nullable"]
                assert any(fk["constrained_columns"] == ["storefront_id", "tenant_id"] for fk in inspector.get_foreign_keys("dashboard_analytics_snapshot"))
            await connection.run_sync(exercise)
        finally:
            # PostgreSQL DDL is transactional; preserve fixture metadata even if
            # an assertion/upgrade fails halfway through the round trip.
            await transaction.rollback()
