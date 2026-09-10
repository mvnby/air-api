from datetime import datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel, select

from models import OrderWorkspaceUsageDaily, Storefront, Tenant
from services.order_workspace_usage_retention import (
    OrderWorkspaceUsageRetentionService,
)


@pytest.mark.asyncio
async def test_retention_purges_expired_usage_for_inactive_storefronts_in_batches(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'usage-retention.db'}")
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)
    sessions = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    now = datetime(2026, 9, 10, 12, 0)
    cutoff = now.date() - timedelta(days=89)

    async with sessions() as session:
        session.add_all([
            Tenant(id=1, slug="mvn", display_name="MVN", status="active", is_system=True),
            Storefront(id=1, tenant_id=1, slug="main", display_name="Main", status="active", is_default=True),
            Storefront(id=2, tenant_id=1, slug="inactive", display_name="Inactive", status="active", is_default=False),
        ])
        await session.flush()
        for storefront_id, day, metric in [
            (1, cutoff - timedelta(days=1), "order_open"),
            (2, cutoff - timedelta(days=2), "documents_open"),
            (2, cutoff, "payments_open"),
        ]:
            session.add(OrderWorkspaceUsageDaily(
                tenant_id=1,
                storefront_id=storefront_id,
                day=day,
                layout_version="workspace_v1",
                workflow="maintenance",
                party_kind="company",
                viewport="desktop",
                metric=metric,
                count=1,
            ))
        await session.commit()

    retention = OrderWorkspaceUsageRetentionService(
        session_factory=sessions,
        batch_size=1,
        now=lambda: now,
    )
    assert await retention.purge_once() == 1
    assert await retention.purge_once() == 1
    assert await retention.purge_once() == 0

    async with sessions() as session:
        rows = list((await session.execute(select(OrderWorkspaceUsageDaily))).scalars())
    assert [(row.storefront_id, row.metric) for row in rows] == [(2, "payments_open")]
    await engine.dispose()
