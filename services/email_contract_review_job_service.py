"""Short-lived in-memory jobs keep long AI reviews outside HTTP proxy deadlines."""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass
from uuid import uuid4

from schemas_contract_review import ContractReviewJobResponse, ContractReviewResponse
from services.email_contract_review_service import ContractReviewInputError, EmailContractReviewService


@dataclass
class _Job:
    owner: str
    created_at: float
    status: str = "running"
    report: ContractReviewResponse | None = None
    error: str | None = None


class EmailContractReviewJobService:
    TTL_SECONDS = 30 * 60
    _jobs: dict[str, _Job] = {}
    _tasks: dict[str, asyncio.Task[None]] = {}
    _lock = asyncio.Lock()
    _semaphore = asyncio.Semaphore(2)

    @classmethod
    async def start(cls, *, owner: str, attachment_id: int, filename: str, content: bytes) -> ContractReviewJobResponse:
        async with cls._lock:
            now = time.monotonic()
            cls._jobs = {
                key: job for key, job in cls._jobs.items()
                if job.status == "running" or now - job.created_at < cls.TTL_SECONDS
            }
            if sum(job.status == "running" for job in cls._jobs.values()) >= 2:
                raise RuntimeError("Сейчас выполняются две проверки; повторите позже")
            job_id = uuid4().hex
            cls._jobs[job_id] = _Job(owner=owner, created_at=now)
            cls._tasks[job_id] = asyncio.create_task(cls._run(job_id, attachment_id, filename, content))
        return ContractReviewJobResponse(job_id=job_id, status="running")

    @classmethod
    async def get(cls, *, job_id: str, owner: str) -> ContractReviewJobResponse | None:
        async with cls._lock:
            job = cls._jobs.get(job_id)
            if job is None or job.owner != owner:
                return None
            if job.status != "running" and time.monotonic() - job.created_at >= cls.TTL_SECONDS:
                cls._jobs.pop(job_id, None)
                return None
            return ContractReviewJobResponse(job_id=job_id, status=job.status, report=job.report, error=job.error)

    @classmethod
    async def _run(cls, job_id: str, attachment_id: int, filename: str, content: bytes) -> None:
        try:
            async with cls._semaphore:
                report = await EmailContractReviewService.review_content(
                    attachment_id=attachment_id, filename=filename, content=content,
                )
            async with cls._lock:
                job = cls._jobs.get(job_id)
                if job is not None:
                    job.status = "completed"
                    job.report = report
        except ContractReviewInputError as exc:
            async with cls._lock:
                job = cls._jobs.get(job_id)
                if job is not None:
                    job.status = "failed"
                    job.error = str(exc)
        except Exception:
            # Provider and document errors can contain private content; never log or expose them here.
            async with cls._lock:
                job = cls._jobs.get(job_id)
                if job is not None:
                    job.status = "failed"
                    job.error = "Не удалось проверить договор. Откройте оригинал и попробуйте ещё раз."
        finally:
            cls._tasks.pop(job_id, None)
