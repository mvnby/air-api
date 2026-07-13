from datetime import datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel

from models import MediaAsset, MediaProcessingJob
from services.media_processing_job_service import MediaProcessingJobService


@pytest.fixture()
async def sqlite_session(tmp_path: Path):
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'media-job-leasing.db'}",
        echo=False,
    )
    async with engine.begin() as connection:
        await connection.run_sync(SQLModel.metadata.create_all)

    session_factory = sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)
    async with session_factory() as session:
        yield session

    await engine.dispose()


async def _create_job(
    session: AsyncSession,
    *,
    job_id: str,
    operation: str = "background_removal",
    provider: str = "rembg",
    rembg_model: str | None = None,
    priority: int = 100,
) -> MediaProcessingJob:
    asset = MediaAsset(
        title=f"Asset {job_id}",
        kind="product",
        url=f"/media/{job_id}.png",
        mime_type="image/png",
    )
    session.add(asset)
    await session.flush()
    now = datetime.now()
    job = MediaProcessingJob(
        job_id=job_id,
        source_asset_id=int(asset.id),
        operation=operation,
        provider=provider,
        rembg_model=rembg_model,
        priority=priority,
        status="queued",
        stage="queued",
        request_payload={},
        result_payload={},
        created_at=now,
        updated_at=now,
    )
    session.add(job)
    await session.commit()
    return job


@pytest.mark.asyncio
async def test_reclaim_rotates_token_and_rejects_stale_attempt(sqlite_session: AsyncSession):
    job = await _create_job(sqlite_session, job_id="reclaim-job")
    job_id = job.job_id
    first_claim = await MediaProcessingJobService.claim_next_job(
        sqlite_session,
        worker_id="same-worker-id",
        capabilities=["background_removal:rembg"],
        lease_seconds=60,
    )
    assert first_claim is not None

    stored_job = await sqlite_session.get(MediaProcessingJob, job_id)
    stored_job.lease_expires_at = datetime.now() - timedelta(seconds=1)
    sqlite_session.add(stored_job)
    await sqlite_session.commit()

    second_claim = await MediaProcessingJobService.claim_next_job(
        sqlite_session,
        worker_id="same-worker-id",
        capabilities=["background_removal:rembg"],
        lease_seconds=60,
    )
    assert second_claim is not None
    assert second_claim["job_id"] == job_id
    assert second_claim["attempts"] == 2
    assert second_claim["lease_token"] != first_claim["lease_token"]

    with pytest.raises(ValueError, match="lease is invalid or expired"):
        await MediaProcessingJobService.complete_job(
            sqlite_session,
            job_id=job_id,
            worker_id="same-worker-id",
            lease_token=first_claim["lease_token"],
            content=b"stale-worker-content",
        )

    with pytest.raises(ValueError, match="lease is invalid or expired"):
        await MediaProcessingJobService.fail_job(
            sqlite_session,
            job_id=job_id,
            worker_id="same-worker-id",
            lease_token=first_claim["lease_token"],
            error="stale failure",
        )

    failed = await MediaProcessingJobService.fail_job(
        sqlite_session,
        job_id=job_id,
        worker_id="same-worker-id",
        lease_token=second_claim["lease_token"],
        error="current attempt failed",
    )
    assert failed["status"] == "failed"


@pytest.mark.asyncio
async def test_expired_lease_cannot_complete_or_fail(sqlite_session: AsyncSession):
    job = await _create_job(sqlite_session, job_id="expired-job")
    job_id = job.job_id
    claimed = await MediaProcessingJobService.claim_next_job(
        sqlite_session,
        worker_id="gpu-box",
        lease_seconds=60,
    )
    assert claimed is not None

    stored_job = await sqlite_session.get(MediaProcessingJob, job_id)
    stored_job.lease_expires_at = datetime.now() - timedelta(seconds=1)
    sqlite_session.add(stored_job)
    await sqlite_session.commit()

    with pytest.raises(ValueError, match="lease is invalid or expired"):
        await MediaProcessingJobService.complete_job(
            sqlite_session,
            job_id=job_id,
            worker_id="gpu-box",
            lease_token=claimed["lease_token"],
            content=b"expired-content",
        )

    with pytest.raises(ValueError, match="lease is invalid or expired"):
        await MediaProcessingJobService.fail_job(
            sqlite_session,
            job_id=job_id,
            worker_id="gpu-box",
            lease_token=claimed["lease_token"],
            error="too late",
        )


@pytest.mark.asyncio
async def test_capabilities_are_filtered_before_claim(sqlite_session: AsyncSession):
    await _create_job(
        sqlite_session,
        job_id="incompatible-upscale",
        operation="upscale",
        provider="external",
        priority=1,
    )
    expected = await _create_job(
        sqlite_session,
        job_id="compatible-rembg",
        operation="background_removal",
        provider="rembg",
        rembg_model="u2net",
        priority=100,
    )

    claimed = await MediaProcessingJobService.claim_next_job(
        sqlite_session,
        worker_id="rembg-worker",
        capabilities=["background_removal:rembg:u2net"],
    )

    assert claimed is not None
    assert claimed["job_id"] == expected.job_id
    assert claimed["lease_token"]


@pytest.mark.asyncio
async def test_regular_job_serialization_does_not_expose_lease_token(sqlite_session: AsyncSession):
    job = await _create_job(sqlite_session, job_id="private-token-job")
    claimed = await MediaProcessingJobService.claim_next_job(
        sqlite_session,
        worker_id="gpu-box",
    )
    assert claimed is not None

    stored_job = await sqlite_session.get(MediaProcessingJob, job.job_id)
    serialized = await MediaProcessingJobService.serialize_job(sqlite_session, stored_job)

    assert "lease_token" not in serialized


@pytest.mark.asyncio
async def test_active_worker_can_renew_lease_but_stale_token_cannot(sqlite_session: AsyncSession):
    job = await _create_job(sqlite_session, job_id="renewable-job")
    claimed = await MediaProcessingJobService.claim_next_job(
        sqlite_session,
        worker_id="gpu-box",
        lease_seconds=60,
    )
    assert claimed is not None
    previous_expiry = claimed["lease_expires_at"]

    renewed = await MediaProcessingJobService.renew_lease(
        sqlite_session,
        job_id=job.job_id,
        worker_id="gpu-box",
        lease_token=claimed["lease_token"],
        lease_seconds=120,
    )

    assert renewed["lease_expires_at"] > previous_expiry
    assert "lease_token" not in renewed
    with pytest.raises(ValueError, match="lease is invalid or expired"):
        await MediaProcessingJobService.renew_lease(
            sqlite_session,
            job_id=job.job_id,
            worker_id="gpu-box",
            lease_token="different-token-with-at-least-thirty-two-chars",
            lease_seconds=120,
        )
