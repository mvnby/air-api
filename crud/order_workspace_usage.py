from datetime import date

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.order_workspace_usage import OrderWorkspaceUsageDaily, USAGE_DIMENSIONS
from models.tenancy import TenantScope


async def increment_daily_usage(session: AsyncSession, rows: list[dict]) -> None:
    statement = postgres_insert(OrderWorkspaceUsageDaily).values(rows)
    await session.execute(statement.on_conflict_do_update(
        index_elements=list(USAGE_DIMENSIONS),
        set_={"count": OrderWorkspaceUsageDaily.count + statement.excluded.count},
    ))


async def prune_daily_usage(session: AsyncSession, scope: TenantScope, before: date) -> None:
    await session.execute(delete(OrderWorkspaceUsageDaily).where(
        OrderWorkspaceUsageDaily.tenant_id == scope.tenant_id,
        OrderWorkspaceUsageDaily.storefront_id == scope.storefront_id,
        OrderWorkspaceUsageDaily.day < before,
    ))


async def purge_expired_daily_usage_batch(
    session: AsyncSession,
    *,
    before: date,
    limit: int = 1_000,
) -> int:
    """Delete one bounded retention batch across every tenant and storefront."""
    statement = (
        select(OrderWorkspaceUsageDaily.id)
        .where(OrderWorkspaceUsageDaily.day < before)
        .order_by(OrderWorkspaceUsageDaily.day.asc(), OrderWorkspaceUsageDaily.id.asc())
        .limit(max(1, min(int(limit), 5_000)))
    )
    if session.get_bind().dialect.name == "postgresql":
        statement = statement.with_for_update(skip_locked=True)
    ids = list((await session.execute(statement)).scalars())
    if not ids:
        return 0
    await session.execute(
        delete(OrderWorkspaceUsageDaily).where(OrderWorkspaceUsageDaily.id.in_(ids))
    )
    return len(ids)


async def list_daily_usage(
    session: AsyncSession, scope: TenantScope, *, since: date, through: date,
    workflow: str | None = None, party_kind: str | None = None, viewport: str | None = None,
) -> list[OrderWorkspaceUsageDaily]:
    statement = select(OrderWorkspaceUsageDaily).where(
        OrderWorkspaceUsageDaily.tenant_id == scope.tenant_id,
        OrderWorkspaceUsageDaily.storefront_id == scope.storefront_id,
        OrderWorkspaceUsageDaily.layout_version == "workspace_v1",
        OrderWorkspaceUsageDaily.day >= since,
        OrderWorkspaceUsageDaily.day <= through,
    )
    for name, value in (("workflow", workflow), ("party_kind", party_kind), ("viewport", viewport)):
        if value is not None:
            statement = statement.where(getattr(OrderWorkspaceUsageDaily, name) == value)
    statement = statement.order_by(OrderWorkspaceUsageDaily.day, OrderWorkspaceUsageDaily.metric)
    return list((await session.execute(statement)).scalars().all())
