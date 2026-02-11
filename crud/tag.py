"""
Repository Layer: Tag Data Access Object (DAO).
"""
from typing import List
from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from models import Tag, TagGroup


class TagDAO:
    """
    Data Access Object for Tag entity.
    """

    @staticmethod
    async def get_all_grouped(session: AsyncSession) -> List[TagGroup]:
        """Fetch all tags grouped by TagGroup."""
        stmt = (
            select(TagGroup)
            .options(selectinload(TagGroup.tags))
            .order_by(TagGroup.sort_order, TagGroup.title)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_by_ids(session: AsyncSession, tag_ids: List[int]) -> List[Tag]:
        """Fetch multiple tags by ID."""
        if not tag_ids:
            return []
        stmt = select(Tag).where(Tag.id.in_(tag_ids))
        result = await session.execute(stmt)
        return list(result.scalars().all())
