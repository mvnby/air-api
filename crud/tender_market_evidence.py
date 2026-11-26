from datetime import datetime

from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from models import TenderMarketEvidence


class TenderMarketEvidenceDAO:
    @staticmethod
    async def get(session: AsyncSession, publication_id: int) -> TenderMarketEvidence | None:
        return await session.get(TenderMarketEvidence, publication_id, populate_existing=True)

    @staticmethod
    async def pending_count(session: AsyncSession) -> int:
        return int(await session.scalar(select(func.count()).select_from(TenderMarketEvidence).where(
            TenderMarketEvidence.status.in_(("queued", "reading")),
        )) or 0)

    @staticmethod
    async def has_running(session: AsyncSession, now: datetime) -> bool:
        return await session.scalar(select(TenderMarketEvidence.publication_id).where(
            TenderMarketEvidence.status == "reading", TenderMarketEvidence.lease_until > now,
        ).limit(1)) is not None

    @staticmethod
    async def claimable(session: AsyncSession, now: datetime) -> TenderMarketEvidence | None:
        return await session.scalar(select(TenderMarketEvidence).where(
            TenderMarketEvidence.available_at <= now,
            or_(TenderMarketEvidence.status == "queued",
                and_(TenderMarketEvidence.status == "reading", TenderMarketEvidence.lease_until <= now)),
        ).order_by(TenderMarketEvidence.available_at, TenderMarketEvidence.publication_id).limit(1))
