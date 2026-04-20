"""Repository helpers for service estimate snapshots."""

from typing import List, Optional, Tuple

from sqlalchemy import func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload
from sqlmodel import select

from models import ServiceEstimate, ServiceEstimateItem


class ServiceEstimateDAO:
    @staticmethod
    async def create(
        session: AsyncSession,
        estimate: ServiceEstimate,
        items: List[ServiceEstimateItem],
    ) -> ServiceEstimate:
        session.add(estimate)
        await session.flush()

        for item in items:
            item.estimate_id = int(estimate.id)
            session.add(item)

        await session.commit()

        stmt = (
            select(ServiceEstimate)
            .where(ServiceEstimate.id == estimate.id)
            .options(selectinload(ServiceEstimate.items))
        )
        result = await session.execute(stmt)
        return result.scalar_one()

    @staticmethod
    async def get_by_id(session: AsyncSession, estimate_id: int) -> Optional[ServiceEstimate]:
        stmt = (
            select(ServiceEstimate)
            .where(ServiceEstimate.id == estimate_id)
            .options(selectinload(ServiceEstimate.items))
        )
        result = await session.execute(stmt)
        return result.scalars().first()

    @staticmethod
    async def list(
        session: AsyncSession,
        page: int = 1,
        limit: int = 20,
    ) -> Tuple[List[ServiceEstimate], int]:
        safe_page = max(1, page)
        safe_limit = max(1, min(limit, 100))
        offset = (safe_page - 1) * safe_limit

        total_stmt = select(func.count()).select_from(ServiceEstimate)
        total_result = await session.execute(total_stmt)
        total = int(total_result.scalar_one() or 0)

        stmt = (
            select(ServiceEstimate)
            .order_by(ServiceEstimate.created_at.desc())
            .offset(offset)
            .limit(safe_limit)
            .options(selectinload(ServiceEstimate.items))
        )
        result = await session.execute(stmt)
        return list(result.scalars().all()), total
