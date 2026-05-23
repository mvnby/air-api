import asyncio
from datetime import datetime
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy import select

from core.database import async_session_maker
from core.logger import logger
from models import CatalogImportJob
from services.importer_service import ImporterService


ACTIVE_STATUSES = {"queued", "running"}


class CatalogImportRuntimeService:
    def __init__(self):
        self._running_task_ids: set[str] = set()
        self._lock = Lock()

    @staticmethod
    def _snapshot(job: CatalogImportJob) -> Dict[str, Any]:
        return {
            "job_id": job.job_id,
            "status": job.status,
            "stage": job.stage,
            "error": job.error,
            "started_at": job.started_at,
            "finished_at": job.finished_at,
            "input_total": job.input_total,
            "total": job.total,
            "processed": job.processed,
            "pending": job.pending,
            "success_count": job.success_count,
            "error_count": job.error_count,
            "current_url": job.current_url,
            "current_title": job.current_title,
            "successes": list(job.successes or []),
            "errors": list(job.errors or []),
        }

    async def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        async with async_session_maker() as session:
            job = await session.get(CatalogImportJob, job_id)
            return self._snapshot(job) if job else None

    async def get_current_job(self) -> Optional[Dict[str, Any]]:
        async with async_session_maker() as session:
            running = (
                await session.execute(
                    select(CatalogImportJob)
                    .where(CatalogImportJob.status == "running")
                    .order_by(CatalogImportJob.updated_at.desc())
                )
            ).scalars().first()
            if running:
                return self._snapshot(running)

            queued = (
                await session.execute(
                    select(CatalogImportJob)
                    .where(CatalogImportJob.status == "queued")
                    .order_by(CatalogImportJob.created_at.asc())
                )
            ).scalars().first()
            if queued:
                return self._snapshot(queued)

            latest = (
                await session.execute(
                    select(CatalogImportJob).order_by(CatalogImportJob.created_at.desc())
                )
            ).scalars().first()
            return self._snapshot(latest) if latest else None

    async def _set_job_fields(self, job_id: str, **updates: Any) -> None:
        async with async_session_maker() as session:
            job = await session.get(CatalogImportJob, job_id)
            if not job:
                return

            for key, value in updates.items():
                if hasattr(job, key):
                    setattr(job, key, value)
            job.updated_at = datetime.now()
            session.add(job)
            await session.commit()

    def _schedule_job(self, job_id: str) -> bool:
        with self._lock:
            if job_id in self._running_task_ids:
                return False
            self._running_task_ids.add(job_id)

        asyncio.create_task(self._run_import_job(job_id))
        return True

    async def _start_next_queued_job(self) -> None:
        async with async_session_maker() as session:
            running = (
                await session.execute(
                    select(CatalogImportJob.job_id).where(CatalogImportJob.status == "running")
                )
            ).scalars().first()
            if running:
                return

            next_job_id = (
                await session.execute(
                    select(CatalogImportJob.job_id)
                    .where(CatalogImportJob.status == "queued")
                    .order_by(CatalogImportJob.created_at.asc())
                )
            ).scalars().first()

        if next_job_id:
            self._schedule_job(next_job_id)

    async def resume_pending_jobs(self) -> None:
        async with async_session_maker() as session:
            stale_running = (
                await session.execute(
                    select(CatalogImportJob).where(CatalogImportJob.status == "running")
                )
            ).scalars().all()
            for job in stale_running:
                job.status = "queued"
                job.stage = "queued"
                job.error = None
                job.updated_at = datetime.now()
                session.add(job)
            await session.commit()

        await self._start_next_queued_job()

    async def start_import(
        self,
        *,
        urls: list[str],
        with_related: bool,
        update_existing: bool,
    ) -> Dict[str, Any]:
        job_id = uuid4().hex
        now = datetime.now()
        job = CatalogImportJob(
            job_id=job_id,
            status="queued",
            stage="queued",
            input_urls=list(urls),
            with_related=with_related,
            update_existing=update_existing,
            input_total=len(urls),
            created_at=now,
            updated_at=now,
        )

        async with async_session_maker() as session:
            session.add(job)
            await session.commit()
            await session.refresh(job)
            snapshot = self._snapshot(job)

        await self._start_next_queued_job()
        return snapshot

    async def _run_import_job(self, job_id: str) -> None:
        importer = ImporterService()

        async with async_session_maker() as session:
            job = await session.get(CatalogImportJob, job_id)
            if not job:
                with self._lock:
                    self._running_task_ids.discard(job_id)
                return

            urls = list(job.input_urls or [])
            with_related = job.with_related
            update_existing = job.update_existing

        async def progress(payload: Dict[str, object]) -> None:
            await self._set_job_fields(
                job_id,
                status="running",
                **payload,
            )

        try:
            await self._set_job_fields(
                job_id,
                status="running",
                stage="expanding",
                error=None,
                started_at=datetime.now(),
                finished_at=None,
                total=0,
                processed=0,
                pending=0,
                success_count=0,
                error_count=0,
                current_url=None,
                current_title=None,
                successes=[],
                errors=[],
            )
            results = await importer.import_products_bulk(
                urls,
                with_related=with_related,
                update_existing=update_existing,
                progress_callback=progress,
            )
            processed = len(results["success"]) + len(results["errors"])
            await self._set_job_fields(
                job_id,
                status="success",
                stage="completed",
                finished_at=datetime.now(),
                total=processed,
                processed=processed,
                pending=0,
                success_count=len(results["success"]),
                error_count=len(results["errors"]),
                successes=results["success"],
                errors=results["errors"],
            )
        except Exception as exc:
            logger.exception("Catalog import job failed: job_id=%s", job_id)
            await self._set_job_fields(
                job_id,
                status="failed",
                stage="failed",
                error=str(exc),
                finished_at=datetime.now(),
            )
        finally:
            with self._lock:
                self._running_task_ids.discard(job_id)
            await self._start_next_queued_job()


catalog_import_runtime_service = CatalogImportRuntimeService()
