from datetime import datetime

from sqlalchemy import select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession

from models import TenderMarketCheckpoint, TenderMarketPublication


class TenderMarketDAO:
    @staticmethod
    async def checkpoint(session: AsyncSession, *, lock: bool = False) -> TenderMarketCheckpoint:
        stmt = select(TenderMarketCheckpoint).where(TenderMarketCheckpoint.id == 1).execution_options(populate_existing=True)
        checkpoint = await session.scalar(stmt.with_for_update() if lock else stmt)
        if checkpoint is None:
            raise RuntimeError("Tender market checkpoint is unavailable")
        return checkpoint

    @staticmethod
    async def publications(session: AsyncSession, identities: list[tuple[str, str]]) -> list[TenderMarketPublication]:
        if not identities:
            return []
        rows = await session.scalars(select(TenderMarketPublication).where(
            tuple_(TenderMarketPublication.source, TenderMarketPublication.external_id).in_(identities),
        ))
        return list(rows)

    @staticmethod
    async def deactivate_unseen(session: AsyncSession, generation: int) -> None:
        await session.execute(update(TenderMarketPublication).where(
            TenderMarketPublication.active.is_(True), TenderMarketPublication.seen_generation < generation,
        ).values(active=False))

    @staticmethod
    async def candidates(
        session: AsyncSession, *, before_id: int | None, now: datetime, limit: int,
    ) -> list[TenderMarketPublication]:
        conditions = (
            TenderMarketPublication.active.is_(True),
            (TenderMarketPublication.deadline_at.is_(None)) | (TenderMarketPublication.deadline_at > now),
        )
        query = select(TenderMarketPublication).where(*conditions)
        if before_id is not None:
            query = query.where(TenderMarketPublication.id < before_id)
        return list(await session.scalars(query.order_by(TenderMarketPublication.id.desc()).limit(limit)))
