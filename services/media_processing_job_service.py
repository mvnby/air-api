from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select

from models import MediaAsset, MediaProcessingJob
from services.media_library_service import SVG_MIME_TYPE, MediaLibraryService


MEDIA_JOB_STATUS_QUEUED = "queued"
MEDIA_JOB_STATUS_RUNNING = "running"
MEDIA_JOB_STATUS_SUCCESS = "success"
MEDIA_JOB_STATUS_FAILED = "failed"
MEDIA_JOB_STATUS_CANCELED = "canceled"

MEDIA_JOB_OPERATION_BACKGROUND_REMOVAL = "background_removal"
MEDIA_JOB_OPERATION_UPSCALE = "upscale"
SUPPORTED_MEDIA_JOB_OPERATIONS = {
    MEDIA_JOB_OPERATION_BACKGROUND_REMOVAL,
    MEDIA_JOB_OPERATION_UPSCALE,
}


class MediaProcessingJobService:
    @staticmethod
    async def create_job(
        session: AsyncSession,
        *,
        source_asset_id: int,
        operation: str = MEDIA_JOB_OPERATION_BACKGROUND_REMOVAL,
        provider: str | None = None,
        rembg_model: str | None = None,
        options: dict[str, Any] | None = None,
        priority: int = 100,
        created_by: str | None = None,
    ) -> dict:
        source = await MediaLibraryService._get_asset_or_raise(session, source_asset_id)
        normalized_operation = MediaProcessingJobService._normalize_operation(operation)
        if source.mime_type == SVG_MIME_TYPE:
            raise ValueError("SVG assets cannot be processed by raster media workers")
        now = datetime.now()
        request_payload = dict(options or {})
        job = MediaProcessingJob(
            job_id=uuid.uuid4().hex,
            source_asset_id=int(source.id or source_asset_id),
            operation=normalized_operation,
            status=MEDIA_JOB_STATUS_QUEUED,
            stage=MEDIA_JOB_STATUS_QUEUED,
            provider=(provider or "rembg").strip() or "rembg",
            rembg_model=(rembg_model or "").strip() or None,
            priority=max(0, int(priority or 100)),
            request_payload=request_payload,
            result_payload={},
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return await MediaProcessingJobService.serialize_job(session, job, source=source)

    @staticmethod
    async def list_jobs(
        session: AsyncSession,
        *,
        status: str | None = None,
        limit: int = 50,
    ) -> dict:
        safe_limit = max(1, min(int(limit or 50), 100))
        stmt = select(MediaProcessingJob)
        if status:
            stmt = stmt.where(MediaProcessingJob.status == status)
        rows = (
            await session.execute(
                stmt.order_by(MediaProcessingJob.created_at.desc()).limit(safe_limit)
            )
        ).scalars().all()
        return {
            "items": [await MediaProcessingJobService.serialize_job(session, row) for row in rows],
            "meta": {
                "total": len(rows),
                "page": 1,
                "limit": safe_limit,
                "pages": 1,
            },
        }

    @staticmethod
    async def claim_next_job(
        session: AsyncSession,
        *,
        worker_id: str,
        capabilities: list[str] | None = None,
        lease_seconds: int = 900,
    ) -> dict | None:
        now = datetime.now()
        capability_set = {item.strip() for item in capabilities or [] if item.strip()}
        stmt = (
            select(MediaProcessingJob)
            .where(
                or_(
                    MediaProcessingJob.status == MEDIA_JOB_STATUS_QUEUED,
                    (
                        (MediaProcessingJob.status == MEDIA_JOB_STATUS_RUNNING)
                        & (MediaProcessingJob.lease_expires_at < now)
                    ),
                )
            )
            .order_by(MediaProcessingJob.priority.asc(), MediaProcessingJob.created_at.asc())
        )
        rows = (await session.execute(stmt)).scalars().all()
        job = MediaProcessingJobService._first_capable_job(rows, capability_set)
        if job is None:
            return None

        job.status = MEDIA_JOB_STATUS_RUNNING
        job.stage = "claimed"
        job.worker_id = worker_id.strip()
        job.attempts = int(job.attempts or 0) + 1
        job.started_at = job.started_at or now
        job.lease_expires_at = now + timedelta(seconds=max(60, int(lease_seconds or 900)))
        job.updated_at = now
        job.error = None
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return await MediaProcessingJobService.serialize_job(session, job)

    @staticmethod
    async def complete_job(
        session: AsyncSession,
        *,
        job_id: str,
        worker_id: str,
        content: bytes,
        filename: str | None = None,
        result_payload: dict[str, Any] | None = None,
    ) -> dict:
        job = await MediaProcessingJobService._get_job_or_raise(session, job_id)
        MediaProcessingJobService._assert_worker_owns_job(job, worker_id)
        source = await session.get(MediaAsset, job.source_asset_id)
        if not source:
            raise LookupError("Source media asset not found")
        if not content:
            raise ValueError("Processed image file is empty")

        variant_type = MediaProcessingJobService._variant_type_for_operation(job.operation)
        stored = await MediaLibraryService._store_image(content, variant_type=variant_type)
        asset = await MediaLibraryService._create_variant_asset(
            session,
            source=source,
            stored=stored,
            variant_type=variant_type,
            title=MediaProcessingJobService._result_title(source, job.operation, filename),
            created_by=job.created_by or worker_id,
        )
        now = datetime.now()
        job.result_asset_id = asset.id
        job.status = MEDIA_JOB_STATUS_SUCCESS
        job.stage = "completed"
        job.finished_at = now
        job.lease_expires_at = None
        job.updated_at = now
        job.result_payload = {
            **dict(result_payload or {}),
            "asset_id": asset.id,
            "url": asset.url,
            "filename": filename,
        }
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return await MediaProcessingJobService.serialize_job(session, job, source=source, result=asset)

    @staticmethod
    async def fail_job(
        session: AsyncSession,
        *,
        job_id: str,
        worker_id: str,
        error: str,
    ) -> dict:
        job = await MediaProcessingJobService._get_job_or_raise(session, job_id)
        MediaProcessingJobService._assert_worker_owns_job(job, worker_id)
        now = datetime.now()
        job.status = MEDIA_JOB_STATUS_FAILED
        job.stage = "failed"
        job.error = (error or "Worker failed").strip()[:2000]
        job.finished_at = now
        job.lease_expires_at = None
        job.updated_at = now
        session.add(job)
        await session.commit()
        await session.refresh(job)
        return await MediaProcessingJobService.serialize_job(session, job)

    @staticmethod
    async def serialize_job(
        session: AsyncSession,
        job: MediaProcessingJob,
        *,
        source: MediaAsset | None = None,
        result: MediaAsset | None = None,
    ) -> dict:
        source_asset = source or await session.get(MediaAsset, job.source_asset_id)
        result_asset = result or (
            await session.get(MediaAsset, job.result_asset_id) if job.result_asset_id else None
        )
        return {
            "job_id": job.job_id,
            "source_asset_id": job.source_asset_id,
            "result_asset_id": job.result_asset_id,
            "operation": job.operation,
            "status": job.status,
            "stage": job.stage,
            "provider": job.provider,
            "rembg_model": job.rembg_model,
            "priority": job.priority,
            "attempts": job.attempts,
            "worker_id": job.worker_id,
            "request_payload": job.request_payload or {},
            "result_payload": job.result_payload or {},
            "error": job.error,
            "source_url": source_asset.url if source_asset else None,
            "source_title": source_asset.title if source_asset else None,
            "result_url": result_asset.url if result_asset else None,
            "created_by": job.created_by,
            "created_at": job.created_at,
            "started_at": job.started_at,
            "lease_expires_at": job.lease_expires_at,
            "finished_at": job.finished_at,
            "updated_at": job.updated_at,
        }

    @staticmethod
    async def _get_job_or_raise(session: AsyncSession, job_id: str) -> MediaProcessingJob:
        job = await session.get(MediaProcessingJob, job_id)
        if not job:
            raise LookupError("Media processing job not found")
        return job

    @staticmethod
    def _normalize_operation(operation: str) -> str:
        normalized = (operation or MEDIA_JOB_OPERATION_BACKGROUND_REMOVAL).strip()
        if normalized not in SUPPORTED_MEDIA_JOB_OPERATIONS:
            raise ValueError(f"Unsupported media processing operation: {normalized}")
        return normalized

    @staticmethod
    def _first_capable_job(
        jobs: list[MediaProcessingJob],
        capabilities: set[str],
    ) -> MediaProcessingJob | None:
        if not capabilities:
            return jobs[0] if jobs else None
        for job in jobs:
            keys = {
                job.operation,
                f"{job.operation}:{job.provider}" if job.provider else job.operation,
                f"{job.operation}:{job.provider}:{job.rembg_model}"
                if job.provider and job.rembg_model
                else job.operation,
            }
            if capabilities.intersection(keys):
                return job
        return None

    @staticmethod
    def _assert_worker_owns_job(job: MediaProcessingJob, worker_id: str) -> None:
        if job.status != MEDIA_JOB_STATUS_RUNNING:
            raise ValueError("Media processing job is not running")
        if job.worker_id and job.worker_id != worker_id:
            raise ValueError("Media processing job is claimed by another worker")

    @staticmethod
    def _variant_type_for_operation(operation: str) -> str:
        if operation == MEDIA_JOB_OPERATION_BACKGROUND_REMOVAL:
            return "background_removed"
        if operation == MEDIA_JOB_OPERATION_UPSCALE:
            return "upscaled"
        return operation

    @staticmethod
    def _result_title(source: MediaAsset, operation: str, filename: str | None) -> str:
        base = source.title or source.source_filename or filename or "Image"
        if operation == MEDIA_JOB_OPERATION_BACKGROUND_REMOVAL:
            return f"{base} без фона"
        if operation == MEDIA_JOB_OPERATION_UPSCALE:
            return f"{base} upscale"
        return f"{base} {operation}"
