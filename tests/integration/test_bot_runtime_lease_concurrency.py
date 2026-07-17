import asyncio
import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from services.bot_runtime_api_service import BotRuntimeApiService


@pytest.mark.asyncio
async def test_postgres_bot_runtime_lease_has_exactly_one_parallel_winner(db_engine):
    assert db_engine.dialect.name == "postgresql"
    factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    name = f"test:bot:{uuid.uuid4().hex}"
    barrier = asyncio.Barrier(12)

    async def acquire(index: int):
        async with factory() as session:
            await barrier.wait()
            return await BotRuntimeApiService.acquire_lease(
                session,
                name=name,
                owner_id=f"owner:{index}",
                ttl_seconds=45,
            )

    results = await asyncio.gather(*(acquire(index) for index in range(12)))
    assert sum(result["acquired"] for result in results) == 1
    winner = next(result for result in results if result["acquired"])

    async with factory() as session:
        assert await BotRuntimeApiService.release_lease(
            session, name=name, owner_id=winner["owner_id"]
        )
