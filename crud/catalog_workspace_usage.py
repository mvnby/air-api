from datetime import date

from sqlalchemy import delete
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models.catalog_workspace_usage import CatalogWorkspaceUsageDaily, CATALOG_USAGE_DIMENSIONS


async def increment_daily_usage(session: AsyncSession, rows: list[dict]) -> None:
    statement = postgres_insert(CatalogWorkspaceUsageDaily).values(rows)
    await session.execute(statement.on_conflict_do_update(
        index_elements=list(CATALOG_USAGE_DIMENSIONS),
        set_={"count": CatalogWorkspaceUsageDaily.count + statement.excluded.count},
    ))


async def prune_daily_usage(session: AsyncSession, *, before: date) -> None:
    await session.execute(delete(CatalogWorkspaceUsageDaily).where(
        CatalogWorkspaceUsageDaily.day < before,
    ))


async def list_daily_usage(
    session: AsyncSession, *, since: date, through: date, layout_version: str | None = None,
    device: str | None = None, action: str | None = None, outcome: str | None = None,
) -> list[CatalogWorkspaceUsageDaily]:
    statement = select(CatalogWorkspaceUsageDaily).where(
        CatalogWorkspaceUsageDaily.day >= since,
        CatalogWorkspaceUsageDaily.day <= through,
    )
    for name, value in (("layout_version", layout_version), ("device", device), ("action", action), ("outcome", outcome)):
        if value is not None:
            statement = statement.where(getattr(CatalogWorkspaceUsageDaily, name) == value)
    statement = statement.order_by(
        CatalogWorkspaceUsageDaily.day,
        CatalogWorkspaceUsageDaily.action,
        CatalogWorkspaceUsageDaily.outcome,
    )
    return list((await session.execute(statement)).scalars().all())
