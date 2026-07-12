from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import and_, false, or_, update
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
        normalized_worker_id = worker_id.strip()
        if not normalized_worker_id:
            raise ValueError("Media worker ID is required")

        now = datetime.now()
        capability_set = {item.strip() for item in capabilities or [] if item.strip()}
        eligible_condition = MediaProcessingJobService._claimable_condition(now)
        stmt = (
            select(MediaProcessingJob)
            .where(eligible_condition)
            .order_by(MediaProcessingJob.priority.asc(), MediaProcessingJob.created_at.asc())
            .limit(1)
        )
        capability_condition = MediaProcessingJobService._capability_condition(capability_set)
        if capability_condition is not None:
            stmt = stmt.where(capability_condition)
        if session.get_bind().dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)

        job = (await session.execute(stmt)).scalar_one_or_none()
        if job is None:
            await session.rollback()
            return None

        lease_token = secrets.token_urlsafe(32)
        lease_expires_at = now + timedelta(seconds=max(60, int(lease_seconds or 900)))
        claim_result = await session.execute(
            update(MediaProcessingJob)
            .where(
                MediaProcessingJob.job_id == job.job_id,
                MediaProcessingJobService._claimable_condition(now),
            )
            .values(
                status=MEDIA_JOB_STATUS_RUNNING,
                stage="claimed",
                worker_id=normalized_worker_id,
                lease_token=lease_token,
                attempts=int(job.attempts or 0) + 1,
                started_at=job.started_at or now,
                lease_expires_at=lease_expires_at,
                updated_at=now,
                error=None,
            )
            .returning(MediaProcessingJob.job_id)
        )
        claimed_job_id = claim_result.scalar_one_or_none()
        if claimed_job_id is None:
            await session.rollback()
            return None

        await session.commit()
        claimed_job = await session.get(MediaProcessingJob, claimed_job_id)
        if claimed_job is None:
            raise LookupError("Claimed media processing job disappeared")
        return await MediaProcessingJobService.serialize_job(
            session,
            claimed_job,
            include_lease_token=True,
        )

    @staticmethod
    async def complete_job(
        session: AsyncSession,
        *,
        job_id: str,
        worker_id: str,
        lease_token: str,
        content: bytes,
        filename: str | None = None,
        result_payload: dict[str, Any] | None = None,
    ) -> dict:
        job = await MediaProcessingJobService._lock_owned_job(
            session,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
        )
        source = await session.get(MediaAsset, job.source_asset_id)
        if not source:
            raise LookupError("Source media asset not found")
        if not content:
            raise ValueError("Processed image file is empty")

        variant_type = MediaProcessingJobService._variant_type_for_operation(job.operation)
        stored = None
        try:
            stored = await MediaLibraryService._store_image(content, variant_type=variant_type)
            asset = await MediaProcessingJobService._create_result_asset(
                session,
                source=source,
                stored=stored,
                variant_type=variant_type,
                title=MediaProcessingJobService._result_title(source, job.operation, filename),
                created_by=job.created_by or worker_id,
            )
            now = datetime.now()
            if job.lease_expires_at is None or job.lease_expires_at <= now:
                raise ValueError("Media processing job lease expired before completion")

            job.result_asset_id = asset.id
            job.status = MEDIA_JOB_STATUS_SUCCESS
            job.stage = "completed"
            job.finished_at = now
            job.lease_expires_at = None
            job.lease_token = None
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
            await session.refresh(asset)
            return await MediaProcessingJobService.serialize_job(
                session,
                job,
                source=source,
                result=asset,
            )
        except Exception:
            await session.rollback()
            if stored is not None:
                try:
                    await MediaLibraryService._remove_file_if_unreferenced(session, stored.url)
                except Exception:
                    pass
            raise

    @staticmethod
    async def renew_lease(
        session: AsyncSession,
        *,
        job_id: str,
        worker_id: str,
        lease_token: str,
        lease_seconds: int = 900,
    ) -> dict:
        now = datetime.now()
        normalized_worker_id, normalized_lease_token = MediaProcessingJobService._normalize_lease_owner(
            worker_id,
            lease_token,
        )
        renew_result = await session.execute(
            update(MediaProcessingJob)
            .where(
                MediaProcessingJob.job_id == job_id,
                MediaProcessingJob.status == MEDIA_JOB_STATUS_RUNNING,
                MediaProcessingJob.worker_id == normalized_worker_id,
                MediaProcessingJob.lease_token == normalized_lease_token,
                MediaProcessingJob.lease_expires_at.is_not(None),
                MediaProcessingJob.lease_expires_at > now,
            )
            .values(
                lease_expires_at=now + timedelta(seconds=max(60, int(lease_seconds or 900))),
                updated_at=now,
            )
            .returning(MediaProcessingJob.job_id)
        )
        renewed_job_id = renew_result.scalar_one_or_none()
        if renewed_job_id is None:
            await MediaProcessingJobService._raise_job_lease_error(session, job_id)

        await session.commit()
        job = await session.get(MediaProcessingJob, renewed_job_id)
        if job is None:
            raise LookupError("Media processing job not found")
        return await MediaProcessingJobService.serialize_job(session, job)

    @staticmethod
    async def fail_job(
        session: AsyncSession,
        *,
        job_id: str,
        worker_id: str,
        lease_token: str,
        error: str,
    ) -> dict:
        now = datetime.now()
        normalized_worker_id, normalized_lease_token = MediaProcessingJobService._normalize_lease_owner(
            worker_id,
            lease_token,
        )
        fail_result = await session.execute(
            update(MediaProcessingJob)
            .where(
                MediaProcessingJob.job_id == job_id,
                MediaProcessingJob.status == MEDIA_JOB_STATUS_RUNNING,
                MediaProcessingJob.worker_id == normalized_worker_id,
                MediaProcessingJob.lease_token == normalized_lease_token,
                MediaProcessingJob.lease_expires_at.is_not(None),
                MediaProcessingJob.lease_expires_at > now,
            )
            .values(
                status=MEDIA_JOB_STATUS_FAILED,
                stage="failed",
                error=(error or "Worker failed").strip()[:2000],
                finished_at=now,
                lease_expires_at=None,
                lease_token=None,
                updated_at=now,
            )
            .returning(MediaProcessingJob.job_id)
        )
        failed_job_id = fail_result.scalar_one_or_none()
        if failed_job_id is None:
            await MediaProcessingJobService._raise_job_lease_error(session, job_id)

        await session.commit()
        job = await session.get(MediaProcessingJob, failed_job_id)
        if job is None:
            raise LookupError("Media processing job not found")
        return await MediaProcessingJobService.serialize_job(session, job)

    @staticmethod
    async def serialize_job(
        session: AsyncSession,
        job: MediaProcessingJob,
        *,
        source: MediaAsset | None = None,
        result: MediaAsset | None = None,
        include_lease_token: bool = False,
    ) -> dict:
        source_asset = source or await session.get(MediaAsset, job.source_asset_id)
        result_asset = result or (
            await session.get(MediaAsset, job.result_asset_id) if job.result_asset_id else None
        )
        payload = {
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
        if include_lease_token:
            if not job.lease_token:
                raise ValueError("Claimed media processing job has no lease token")
            payload["lease_token"] = job.lease_token
        return payload

    @staticmethod
    def _normalize_operation(operation: str) -> str:
        normalized = (operation or MEDIA_JOB_OPERATION_BACKGROUND_REMOVAL).strip()
        if normalized not in SUPPORTED_MEDIA_JOB_OPERATIONS:
            raise ValueError(f"Unsupported media processing operation: {normalized}")
        return normalized

    @staticmethod
    def _claimable_condition(now: datetime):
        return or_(
            MediaProcessingJob.status == MEDIA_JOB_STATUS_QUEUED,
            and_(
                MediaProcessingJob.status == MEDIA_JOB_STATUS_RUNNING,
                MediaProcessingJob.lease_expires_at.is_not(None),
                MediaProcessingJob.lease_expires_at <= now,
            ),
        )

    @staticmethod
    def _capability_condition(capabilities: set[str]):
        if not capabilities:
            return None

        predicates = []
        for capability in capabilities:
            operation, separator, provider_and_model = capability.partition(":")
            if not operation:
                continue
            predicate = MediaProcessingJob.operation == operation
            if separator:
                provider, model_separator, model = provider_and_model.partition(":")
                if not provider:
                    continue
                predicate = and_(predicate, MediaProcessingJob.provider == provider)
                if model_separator:
                    if not model:
                        continue
                    predicate = and_(predicate, MediaProcessingJob.rembg_model == model)
            predicates.append(predicate)

        return or_(*predicates) if predicates else false()

    @staticmethod
    def _normalize_lease_owner(worker_id: str, lease_token: str) -> tuple[str, str]:
        normalized_worker_id = str(worker_id or "").strip()
        normalized_lease_token = str(lease_token or "").strip()
        if not normalized_worker_id:
            raise ValueError("Media worker ID is required")
        if not normalized_lease_token:
            raise ValueError("Media processing job lease token is required")
        return normalized_worker_id, normalized_lease_token

    @staticmethod
    async def _lock_owned_job(
        session: AsyncSession,
        *,
        job_id: str,
        worker_id: str,
        lease_token: str,
    ) -> MediaProcessingJob:
        normalized_worker_id, normalized_lease_token = MediaProcessingJobService._normalize_lease_owner(
            worker_id,
            lease_token,
        )
        now = datetime.now()
        stmt = select(MediaProcessingJob).where(
            MediaProcessingJob.job_id == job_id,
            MediaProcessingJob.status == MEDIA_JOB_STATUS_RUNNING,
            MediaProcessingJob.worker_id == normalized_worker_id,
            MediaProcessingJob.lease_token == normalized_lease_token,
            MediaProcessingJob.lease_expires_at.is_not(None),
            MediaProcessingJob.lease_expires_at > now,
        )
        if session.get_bind().dialect.name == "postgresql":
            stmt = stmt.with_for_update()
        job = (await session.execute(stmt)).scalar_one_or_none()
        if job is None:
            await MediaProcessingJobService._raise_job_lease_error(session, job_id)
        return job

    @staticmethod
    async def _raise_job_lease_error(session: AsyncSession, job_id: str) -> None:
        exists = await session.scalar(
            select(MediaProcessingJob.job_id).where(MediaProcessingJob.job_id == job_id)
        )
        await session.rollback()
        if exists is None:
            raise LookupError("Media processing job not found")
        raise ValueError("Media processing job lease is invalid or expired")

    @staticmethod
    async def _create_result_asset(
        session: AsyncSession,
        *,
        source: MediaAsset,
        stored: Any,
        variant_type: str,
        title: str,
        created_by: str | None,
    ) -> MediaAsset:
        asset = MediaAsset(
            parent_asset_id=source.id,
            title=title,
            alt_text=source.alt_text,
            description=source.description,
            kind=source.kind,
            tags=list(source.tags or []),
            variant_type=variant_type,
            url=stored.url,
            original_url=source.original_url or source.url,
            source_filename=source.source_filename,
            mime_type=stored.mime_type,
            storage_provider=stored.storage_provider,
            processing_status="ready",
            content_hash=stored.content_hash,
            width=stored.width,
            height=stored.height,
            size_bytes=stored.size_bytes,
            created_by=created_by,
        )
        session.add(asset)
        await session.flush()
        return asset

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
