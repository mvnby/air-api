import asyncio
from datetime import datetime

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import sessionmaker

from models import MediaAsset, MediaProcessingJob
from services.media_processing_job_service import MediaProcessingJobService


async def _seed_jobs(db_engine, count: int) -> None:
    session_factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        for index in range(count):
            asset = MediaAsset(
                title=f"Concurrent asset {index}",
                kind="product",
                url=f"/media/concurrent-{index}.png",
                mime_type="image/png",
            )
            session.add(asset)
            await session.flush()
            now = datetime.now()
            session.add(
                MediaProcessingJob(
                    job_id=f"concurrent-job-{index}",
                    source_asset_id=int(asset.id),
                    operation="background_removal",
                    provider="rembg",
                    priority=100,
                    status="queued",
                    stage="queued",
                    request_payload={},
                    result_payload={},
                    created_at=now,
                    updated_at=now,
                )
            )
        await session.commit()


async def _claim_concurrently(db_engine):
    session_factory = sessionmaker(bind=db_engine, class_=AsyncSession, expire_on_commit=False)
    barrier = asyncio.Barrier(2)

    async def claim(worker_id: str):
        async with session_factory() as session:
            await barrier.wait()
            return await MediaProcessingJobService.claim_next_job(
                session,
                worker_id=worker_id,
                capabilities=["background_removal:rembg"],
            )

    return await asyncio.gather(claim("worker-a"), claim("worker-b"))


@pytest.mark.asyncio
async def test_postgres_concurrent_claims_lock_different_jobs(db_engine):
    assert db_engine.dialect.name == "postgresql"
    await _seed_jobs(db_engine, count=2)

    claims = await _claim_concurrently(db_engine)

    assert all(claim is not None for claim in claims)
    assert len({claim["job_id"] for claim in claims}) == 2
    assert all(claim["lease_token"] for claim in claims)


@pytest.mark.asyncio
async def test_postgres_concurrent_claims_return_single_job_once(db_engine):
    assert db_engine.dialect.name == "postgresql"
    await _seed_jobs(db_engine, count=1)

    claims = await _claim_concurrently(db_engine)
    claimed = [claim for claim in claims if claim is not None]

    assert len(claimed) == 1
    assert claimed[0]["job_id"] == "concurrent-job-0"
    assert claimed[0]["attempts"] == 1
