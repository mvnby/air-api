"""Persistence serialization for a delivered incoming source event."""
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import Lead


class IncomingEventDAO:
    @staticmethod
    async def lock_source(session: AsyncSession, key: str) -> None:
        if session.get_bind().dialect.name == "postgresql":
            lock_id = int.from_bytes(bytes.fromhex(key[:16]), "big", signed=True)
            await session.execute(text("SELECT pg_advisory_xact_lock(:key)"), {"key": lock_id})

    @staticmethod
    async def get_by_key(session: AsyncSession, key: str) -> Lead | None:
        return (await session.execute(select(Lead).where(Lead.intake_event_key == key))).scalar_one_or_none()
