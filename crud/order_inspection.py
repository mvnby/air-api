"""Queries for the append-only order inspection register."""

from collections.abc import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import func, select

from models.order_inspection import OrderInspectionRevision


async def latest_inspections(
    session: AsyncSession, *, order_id: int, site_id: int, equipment_ids: Sequence[int],
) -> dict[int, OrderInspectionRevision]:
    revision = OrderInspectionRevision
    latest = (
        select(revision.equipment_id, func.max(revision.version).label("version"))
        .where(revision.order_id == order_id, revision.site_id == site_id, revision.equipment_id.in_(equipment_ids))
        .group_by(revision.equipment_id)
        .subquery()
    )
    selected = select(revision).join(
        latest, (revision.equipment_id == latest.c.equipment_id) & (revision.version == latest.c.version),
    ).where(revision.order_id == order_id, revision.site_id == site_id)
    return {row.equipment_id: row for row in (await session.scalars(selected)).all()}


async def get_inspection(
    session: AsyncSession, *, order_id: int, site_id: int, equipment_id: int, version: int,
) -> OrderInspectionRevision | None:
    return await session.scalar(
        select(OrderInspectionRevision).where(
            OrderInspectionRevision.order_id == order_id,
            OrderInspectionRevision.site_id == site_id,
            OrderInspectionRevision.equipment_id == equipment_id,
            OrderInspectionRevision.version == version,
        )
    )


async def append_inspection(
    session: AsyncSession, *, order_id: int, site_id: int, equipment_id: int,
    version: int, staff_user_id: int, username: str, facts: dict,
) -> OrderInspectionRevision:
    row = OrderInspectionRevision(
        order_id=order_id, site_id=site_id, equipment_id=equipment_id,
        version=version, actor_staff_user_id=staff_user_id, recorded_by=username, facts=facts,
    )
    session.add(row)
    await session.flush()
    return row
