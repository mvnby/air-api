"""
Infrastructure Layer: Database Connection and Session Management.
This module ONLY handles connection setup. No business logic.
"""
from sqlmodel import SQLModel
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from typing import AsyncGenerator

from core.config import settings

# Async Engine
engine = create_async_engine(
    settings.DATABASE_URL, 
    echo=False, 
    connect_args={"check_same_thread": False}
)

# Async Session Factory
async_session_maker = sessionmaker(
    engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)


async def init_db():
    """Initialize database schema."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency for FastAPI: Yields a session for the request lifecycle.
    Usage:
        @router.get("/items")
        async def get_items(session: AsyncSession = Depends(get_session)):
            ...
    """
    async with async_session_maker() as session:
        yield session
