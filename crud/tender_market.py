from datetime import datetime

from sqlalchemy import and_, or_, select, tuple_, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from models import TenderMarketCheckpoint, TenderMarketPublication


class TenderMarketDAO:
    @staticmethod
    async def get(session: AsyncSession, publication_id: int) -> TenderMarketPublication | None:
        return await session.get(TenderMarketPublication, publication_id, populate_existing=True)

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
        publication = TenderMarketPublication
        alternative = aliased(publication)
        better_source = and_(
            alternative.source != "gias_by", publication.source == "gias_by",
        )
        equivalent_source = or_(alternative.source == publication.source, and_(
            alternative.source != "gias_by", publication.source != "gias_by",
        ))
        preferred = select(alternative.id).where(
            alternative.canonical_url == publication.canonical_url, alternative.active.is_(True),
            (alternative.deadline_at.is_(None)) | (alternative.deadline_at > now),
            or_(better_source, and_(equivalent_source, alternative.id > publication.id)),
        ).correlate(publication)
        conditions = (
            publication.active.is_(True),
            (publication.deadline_at.is_(None)) | (publication.deadline_at > now),
            ~preferred.exists(),
        )
        query = select(publication).where(*conditions)
        if before_id is not None:
            query = query.where(publication.id < before_id)
        return list(await session.scalars(query.order_by(publication.id.desc()).limit(limit)))
