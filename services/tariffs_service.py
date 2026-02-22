import logging
from typing import List, Optional

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from models import InstallationRate
from schemas import ManagerTariffCreatePayload, ManagerTariffUpdatePayload

logger = logging.getLogger(__name__)

class TariffsService:

    @staticmethod
    async def get_all_tariffs(session: AsyncSession) -> List[InstallationRate]:
        stmt = select(InstallationRate).order_by(InstallationRate.category, InstallationRate.power_range)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_tariff_by_id(session: AsyncSession, tariff_id: int) -> InstallationRate:
        tariff = await session.get(InstallationRate, tariff_id)
        if not tariff:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Tariff not found")
        return tariff

    @staticmethod
    async def create_tariff(session: AsyncSession, payload: ManagerTariffCreatePayload) -> InstallationRate:
        tariff = InstallationRate(**payload.model_dump())
        session.add(tariff)
        await session.commit()
        await session.refresh(tariff)
        return tariff

    @staticmethod
    async def update_tariff(session: AsyncSession, tariff_id: int, payload: ManagerTariffUpdatePayload) -> InstallationRate:
        tariff = await TariffsService.get_tariff_by_id(session, tariff_id)
        
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(tariff, key, value)
            
        session.add(tariff)
        await session.commit()
        await session.refresh(tariff)
        return tariff

    @staticmethod
    async def delete_tariff(session: AsyncSession, tariff_id: int) -> None:
        tariff = await TariffsService.get_tariff_by_id(session, tariff_id)
        await session.delete(tariff)
        await session.commit()
