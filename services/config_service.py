"""
Service Layer: Global Configuration Management.
"""
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select, func

from core.database import async_session_maker
from models import GlobalConfig

class ConfigService:
    """Service for managing GlobalConfig."""

    @staticmethod
    async def set_config(key: str, value: str) -> GlobalConfig:
        """
        Create or update a global configuration entry.
        
        Args:
            key: Configuration key.
            value: Configuration value.
            
        Returns:
            The updated or created GlobalConfig object.
        """
        async with async_session_maker() as session:
            stmt = select(GlobalConfig).where(GlobalConfig.key == key)
            res = await session.execute(stmt)
            config = res.scalar_one_or_none()
            
            if not config:
                config = GlobalConfig(key=key, value=value)
                session.add(config)
            else:
                config.value = value
                config.updated_at = func.now()
            
            await session.commit()
            await session.refresh(config)
            return config
