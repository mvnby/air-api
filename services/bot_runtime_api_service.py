"""Durable bot FSM state and short-lived process leases behind the API boundary."""

from datetime import datetime, timedelta
from typing import Any

from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import BotFsmState, BotRuntimeLease


class BotRuntimeApiService:
    @staticmethod
    async def get_fsm_state(
        session: AsyncSession, *, storage_key: str
    ) -> dict[str, Any]:
        row = await session.get(BotFsmState, storage_key)
        return {
            "state": row.state if row else None,
            "data": dict(row.data or {}) if row else {},
        }

    @classmethod
    async def update_fsm_state(
        cls,
        session: AsyncSession,
        *,
        storage_key: str,
        bot_id: int,
        chat_id: int,
        user_id: int,
        thread_id: int | None,
        business_connection_id: str | None,
        destiny: str,
        write_state: bool,
        state: str | None,
        write_data: bool,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        for attempt in range(2):
            row = (
                await session.execute(
                    select(BotFsmState)
                    .where(BotFsmState.storage_key == storage_key)
                    .with_for_update()
                )
            ).scalars().first()
            if row is None:
                row = BotFsmState(
                    storage_key=storage_key,
                    bot_id=bot_id,
                    chat_id=chat_id,
                    user_id=user_id,
                    thread_id=thread_id,
                    business_connection_id=business_connection_id,
                    destiny=destiny,
                )
            if write_state:
                row.state = state
            if write_data:
                row.data = data
            row.updated_at = datetime.now()

            if row.state is None and not row.data:
                persisted = await session.get(BotFsmState, storage_key)
                if persisted is not None:
                    await session.delete(persisted)
            else:
                session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                if attempt == 0:
                    continue
                raise
            return await cls.get_fsm_state(session, storage_key=storage_key)
        raise RuntimeError("FSM state update retry exhausted")

    @staticmethod
    async def acquire_lease(
        session: AsyncSession,
        *,
        name: str,
        owner_id: str,
        ttl_seconds: int,
    ) -> dict[str, Any]:
        for attempt in range(2):
            now = datetime.now()
            expires_at = now + timedelta(seconds=ttl_seconds)
            row = (
                await session.execute(
                    select(BotRuntimeLease)
                    .where(BotRuntimeLease.name == name)
                    .with_for_update()
                )
            ).scalars().first()
            if row is not None and row.owner_id != owner_id and row.expires_at > now:
                return {
                    "name": name,
                    "owner_id": owner_id,
                    "acquired": False,
                    "expires_at": row.expires_at,
                }
            if row is None:
                row = BotRuntimeLease(
                    name=name,
                    owner_id=owner_id,
                    expires_at=expires_at,
                    updated_at=now,
                )
            else:
                row.owner_id = owner_id
                row.expires_at = expires_at
                row.updated_at = now
            session.add(row)
            try:
                await session.commit()
            except IntegrityError:
                await session.rollback()
                if attempt == 0:
                    continue
                raise
            return {
                "name": name,
                "owner_id": owner_id,
                "acquired": True,
                "expires_at": expires_at,
            }
        raise RuntimeError("Runtime lease acquisition retry exhausted")

    @staticmethod
    async def release_lease(
        session: AsyncSession, *, name: str, owner_id: str
    ) -> bool:
        row = (
            await session.execute(
                select(BotRuntimeLease)
                .where(BotRuntimeLease.name == name)
                .with_for_update()
            )
        ).scalars().first()
        if row is None or row.owner_id != owner_id:
            return False
        await session.delete(row)
        await session.commit()
        return True
