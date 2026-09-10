"""Bounded retention for content-free order-workspace usage aggregates."""

from __future__ import annotations

from collections.abc import Callable
from datetime import date, datetime, timedelta
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from core.database import async_session_maker
from crud.order_workspace_usage import purge_expired_daily_usage_batch
from services.order_workspace_usage_service import (
    USAGE_RETENTION_DAYS,
    USAGE_TIMEZONE,
)


class AsyncSessionFactory(Protocol):
    def __call__(self) -> AsyncSession: ...


class OrderWorkspaceUsageRetentionService:
    """Own short transactions so inactive storefronts also meet the retention rule."""

    def __init__(
        self,
        *,
        session_factory: AsyncSessionFactory = async_session_maker,
        batch_size: int = 1_000,
        now: Callable[[], datetime] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._batch_size = max(1, min(int(batch_size), 5_000))
        self._now = now or (lambda: datetime.now(USAGE_TIMEZONE))

    def cutoff_day(self) -> date:
        current = self._now()
        if current.tzinfo is None:
            current = current.replace(tzinfo=USAGE_TIMEZONE)
        else:
            current = current.astimezone(USAGE_TIMEZONE)
        return current.date() - timedelta(days=USAGE_RETENTION_DAYS - 1)

    async def purge_once(self) -> int:
        async with self._session_factory() as session:
            deleted = await purge_expired_daily_usage_batch(
                session,
                before=self.cutoff_day(),
                limit=self._batch_size,
            )
            await session.commit()
            return deleted
