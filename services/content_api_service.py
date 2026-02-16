"""Service-layer helpers for public content/services/config endpoints."""

from typing import Dict, List

from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import GlobalConfig, Service


class ContentApiService:
    @staticmethod
    async def get_active_services(session: AsyncSession) -> List[Service]:
        stmt = select(Service).where(Service.is_active == True).order_by(Service.id)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_service_options(
        session: AsyncSession,
        category: str = "installation_option",
    ) -> List[Service]:
        stmt = (
            select(Service)
            .where(Service.is_active == True)
            .where(Service.category == category)
            .order_by(Service.base_price)
        )
        result = await session.execute(stmt)
        return list(result.scalars().all())

    @staticmethod
    async def get_global_config_map(session: AsyncSession) -> Dict[str, str]:
        stmt = select(GlobalConfig)
        result = await session.execute(stmt)
        configs = result.scalars().all()
        return {config.key: config.value for config in configs}
