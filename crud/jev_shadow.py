"""Persistence helpers for bounded shadow sampling, reservations and reports."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from sqlalchemy import func
from sqlmodel import select

from models.jev_shadow import JevConnection, JevShadowSample
from models.tenancy import Tenant

MAX_PENDING = 500
RESERVATION_USD = Decimal("0.002688")  # 64k input tokens at $0.042/M; output is free.


def reset_budget_day(connection, now):
    if connection.budget_day != now.date():
        connection.budget_day, connection.daily_requests = now.date(), 0
        connection.budget_used_usd = Decimal("0")


def budget_available(connection, *, max_daily_requests):
    return connection.daily_requests < max_daily_requests and connection.budget_used_usd + RESERVATION_USD <= connection.daily_budget_usd


def reserve_request(connection):
    connection.daily_requests += 1
    connection.budget_used_usd += RESERVATION_USD


async def pending_count(session):
    return int((await session.execute(select(func.count()).select_from(JevShadowSample).where(
        JevShadowSample.status.in_(["queued", "running"])))).scalar_one())


async def is_system_tenant(session, tenant_id):
    return (await session.execute(select(Tenant.is_system).where(Tenant.id == tenant_id, Tenant.status == "active"))).scalar_one_or_none() is True


async def sample_exists(session, *, tenant_id, storefront_id, source, sample_key):
    return (await session.execute(select(JevShadowSample.id).where(
        JevShadowSample.tenant_id == tenant_id, JevShadowSample.storefront_id == storefront_id,
        JevShadowSample.source == source, JevShadowSample.sample_key == sample_key))).scalar_one_or_none() is not None


async def claim_next(session, *, max_daily_requests):
    connection = await session.get(JevConnection, 1, with_for_update=True)
    if not connection or not connection.enabled or not connection.encrypted_credentials:
        return None
    now = datetime.now(timezone.utc)
    # Never repeat an ambiguous call after a crash. Its worst-case reservation remains charged.
    abandoned = (await session.execute(select(JevShadowSample).where(
        JevShadowSample.status == "running", JevShadowSample.started_at < now - timedelta(minutes=2)
    ).with_for_update(skip_locked=True).limit(50))).scalars().all()
    for row in abandoned:
        row.status, row.error_code = "failed", "worker_interrupted"
        session.add(row)
    reset_budget_day(connection, now)
    session.add(connection)
    if not budget_available(connection, max_daily_requests=max_daily_requests):
        return None
    sample = (await session.execute(select(JevShadowSample).join(Tenant, Tenant.id == JevShadowSample.tenant_id).where(
        JevShadowSample.status == "queued", Tenant.is_system.is_(True), Tenant.status == "active"
    ).order_by(JevShadowSample.id).with_for_update(skip_locked=True).limit(1))).scalar_one_or_none()
    if sample is None:
        return None
    sample.status, sample.started_at, sample.budget_day = "running", now, now.date()
    reserve_request(connection)
    session.add(sample)
    return connection, sample


async def status_counts(session, *, tenant_id, source=None):
    statement = select(JevShadowSample.status, func.count()).where(JevShadowSample.tenant_id == tenant_id)
    if source:
        statement = statement.where(JevShadowSample.source == source)
    return dict((await session.execute(statement.group_by(JevShadowSample.status))).all())


async def completed_metrics(session, *, tenant_id, source=None):
    statement = select(JevShadowSample).where(JevShadowSample.tenant_id == tenant_id, JevShadowSample.status == "completed")
    if source:
        statement = statement.where(JevShadowSample.source == source)
    # Aggregate in SQL; the sample store grows over time.
    comparable = statement.where(JevShadowSample.primary_is_relevant.is_not(None)).subquery()
    totals = statement.subquery()
    aggregate = (await session.execute(select(func.coalesce(func.sum(totals.c.estimated_usd), 0),
        func.coalesce(func.sum(totals.c.input_tokens), 0)))).one()
    agreements = int((await session.execute(select(func.count()).select_from(comparable).where(
        comparable.c.primary_is_relevant == comparable.c.jev_is_relevant))).scalar_one())
    count = int((await session.execute(select(func.count()).select_from(comparable))).scalar_one())
    # Median over the latest 1000 successes is bounded and is explicitly named in docs.
    durations = (await session.execute(statement.with_only_columns(JevShadowSample.duration_ms).order_by(
        JevShadowSample.id.desc()).limit(1000))).scalars().all()
    return aggregate, count, agreements, [n for n in durations if n is not None]


async def report_items(session, *, tenant_id, source=None, disagreements_only=False, limit=20):
    statement = select(JevShadowSample).where(JevShadowSample.tenant_id == tenant_id)
    if source:
        statement = statement.where(JevShadowSample.source == source)
    if disagreements_only:
        statement = statement.where(JevShadowSample.status == "completed", JevShadowSample.primary_is_relevant.is_not(None),
                                    JevShadowSample.primary_is_relevant != JevShadowSample.jev_is_relevant)
    return (await session.execute(statement.order_by(JevShadowSample.id.desc()).limit(limit))).scalars().all()
