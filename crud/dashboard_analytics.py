"""Snapshot persistence and short atomic leases; HTTP never runs in this layer."""
from datetime import datetime, timedelta
from uuid import uuid4

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from models.dashboard_analytics import DashboardAnalyticsSnapshot as Snapshot


async def read_candidates(session, *, tenant_id, storefront_id, configurations, periods):
    if not configurations:
        return []
    predicates = [and_(Snapshot.provider == c.provider, Snapshot.configuration_revision == c.revision) for c in configurations]
    windows = [and_(Snapshot.period_start == start, Snapshot.period_end <= end) for start, end in periods]
    # At most two records per source/window: most recent attempt, last success.
    partitions = [Snapshot.provider, Snapshot.configuration_revision, Snapshot.period_start]
    ranked = select(
        Snapshot.key,
        func.row_number().over(partition_by=partitions, order_by=Snapshot.period_end.desc()).label("latest"),
        func.row_number().over(partition_by=partitions, order_by=[Snapshot.last_success_at.is_(None), Snapshot.period_end.desc()]).label("success"),
    ).where(Snapshot.tenant_id == tenant_id, Snapshot.storefront_id == storefront_id,
            Snapshot.schema_version == 1, or_(*predicates), or_(*windows)).subquery()
    return (await session.execute(select(Snapshot).join(ranked, ranked.c.key == Snapshot.key).where(or_(ranked.c.latest == 1, ranked.c.success == 1)))).scalars().all()


async def exact_rows(session, keys):
    if not keys:
        return {}
    rows = (await session.execute(select(Snapshot).where(Snapshot.key.in_(keys)).execution_options(populate_existing=True))).scalars().all()
    return {row.key: row for row in rows}


async def claim(session, *, values, now: datetime, lease_seconds=90):
    dialect = session.get_bind().dialect.name
    insert = sqlite_insert if dialect == "sqlite" else pg_insert
    await session.execute(insert(Snapshot).values(**values).on_conflict_do_nothing(index_elements=["key"]))
    token = uuid4().hex
    result = await session.execute(update(Snapshot).where(
        Snapshot.key == values["key"],
        or_(Snapshot.next_retry_at.is_(None), Snapshot.next_retry_at <= now),
        or_(Snapshot.lease_until.is_(None), Snapshot.lease_until <= now),
    ).execution_options(synchronize_session=False).values(lease_token=token, lease_until=now + timedelta(seconds=lease_seconds), last_attempt_at=now).returning(Snapshot.key))
    claimed = result.scalar_one_or_none() is not None
    await session.commit()
    return token if claimed else None


async def finish(session, *, key, token, now, payload=None, error_code=None, ttl_seconds=3600):
    row = (await session.execute(select(Snapshot).where(Snapshot.key == key, Snapshot.lease_token == token).with_for_update().execution_options(populate_existing=True))).scalar_one_or_none()
    if row is None:
        return False
    if error_code:
        row.failure_count += 1
        row.error_code = error_code
        row.next_retry_at = now + timedelta(seconds=min(3600, 60 * 2 ** min(row.failure_count - 1, 6)))
    else:
        row.payload = payload
        row.last_success_at = now
        row.error_code = None
        row.failure_count = 0
        row.next_retry_at = now + timedelta(seconds=ttl_seconds)
    row.lease_token = None
    row.lease_until = None
    session.add(row)
    await session.commit()
    return True


async def connection_rows(session, scope):
    from models.analytics_connection import AnalyticsConnection
    return (await session.execute(select(AnalyticsConnection).where(
        AnalyticsConnection.tenant_id == scope.tenant_id,
        AnalyticsConnection.storefront_id == scope.storefront_id,
    ).execution_options(populate_existing=True))).scalars().all()


async def active_scopes(session):
    from models.tenancy import Storefront, Tenant, TenantScope
    rows = (await session.execute(select(Storefront.tenant_id, Storefront.id, Tenant.is_system)
        .join(Tenant, Tenant.id == Storefront.tenant_id)
        .where(Tenant.status == "active", Storefront.status == "active", Tenant.demo_read_only.is_(False)))).all()
    return [TenantScope(tenant_id=t, storefront_id=s, is_system=system) for t, s, system in rows]
