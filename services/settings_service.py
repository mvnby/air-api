import logging
from typing import List, Optional
from datetime import datetime

from sqlmodel import select
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status

from models import GlobalConfig
from schemas import ManagerSettingUpdatePayload

logger = logging.getLogger(__name__)

class SettingsService:

    @staticmethod
    async def get_all_settings(session: AsyncSession) -> List[GlobalConfig]:
        stmt = select(GlobalConfig).order_by(GlobalConfig.key)
        res = await session.execute(stmt)
        return list(res.scalars().all())

    @staticmethod
    async def get_setting_by_key(session: AsyncSession, key: str) -> GlobalConfig:
        stmt = select(GlobalConfig).where(GlobalConfig.key == key)
        res = await session.execute(stmt)
        setting = res.scalar_one_or_none()
        if not setting:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Setting not found")
        return setting

    @staticmethod
    async def update_setting(session: AsyncSession, key: str, payload: ManagerSettingUpdatePayload) -> GlobalConfig:
        setting = await SettingsService.get_setting_by_key(session, key)
        
        setting.value = payload.value
        if payload.description is not None:
            setting.description = payload.description
            
        setting.updated_at = datetime.now()
        
        session.add(setting)
        await session.commit()
        await session.refresh(setting)
        
        return setting
