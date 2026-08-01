from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import PublicWriteIdempotency


class PublicWriteIdempotencyRetentionService:
    @staticmethod
    async def delete_expired_batch(
        session: AsyncSession,
        *,
        now: datetime | None = None,
        limit: int = 1000,
    ) -> int:
        cutoff = now or datetime.now(timezone.utc)
        statement = (
            select(PublicWriteIdempotency.id)
            .where(PublicWriteIdempotency.expires_at <= cutoff)
            .order_by(PublicWriteIdempotency.expires_at.asc())
            .limit(max(1, min(int(limit), 5000)))
        )
        if session.get_bind().dialect.name == "postgresql":
            statement = statement.with_for_update(skip_locked=True)
        ids = list((await session.execute(statement)).scalars())
        if not ids:
            return 0
        await session.execute(
            delete(PublicWriteIdempotency).where(
                PublicWriteIdempotency.id.in_(ids)
            )
        )
        return len(ids)
