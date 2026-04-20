import asyncio
from datetime import datetime
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4

from core.logger import logger
from services.backup_service import backup_service


class BackupRunConflictError(Exception):
    pass


class BackupRunRuntimeService:
    def __init__(self):
        self._jobs: Dict[str, Dict[str, Any]] = {}
        self._active_job_id: Optional[str] = None
        self._lock = Lock()

    def _snapshot(self, job: Dict[str, Any]) -> Dict[str, Any]:
        return dict(job)

    def _get_job_unsafe(self, job_id: str) -> Optional[Dict[str, Any]]:
        return self._jobs.get(job_id)

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            job = self._get_job_unsafe(job_id)
            return self._snapshot(job) if job else None

    def has_active_job(self) -> bool:
        with self._lock:
            if not self._active_job_id:
                return False
            job = self._get_job_unsafe(self._active_job_id)
            return bool(job and job.get("status") in {"queued", "running"})

    def _set_job_fields(self, job_id: str, **updates: Any) -> None:
        with self._lock:
            job = self._get_job_unsafe(job_id)
            if not job:
                return
            job.update(updates)
            job["updated_at"] = datetime.now()

    def _clear_active_if_needed(self, job_id: str) -> None:
        with self._lock:
            if self._active_job_id == job_id:
                self._active_job_id = None

    async def start_backup(self) -> Dict[str, Any]:
        with self._lock:
            if self._active_job_id:
                active = self._get_job_unsafe(self._active_job_id)
                if active and active.get("status") in {"queued", "running"}:
                    raise BackupRunConflictError("Another backup job is already running")

            job_id = uuid4().hex
            now = datetime.now()
            payload = {
                "job_id": job_id,
                "status": "queued",
                "stage": "queued",
                "error": None,
                "started_at": None,
                "finished_at": None,
                "updated_at": now,
            }
            self._jobs[job_id] = payload
            self._active_job_id = job_id

        asyncio.create_task(self._run_backup_job(job_id))
        return self.get_job(job_id) or payload

    async def _run_backup_job(self, job_id: str):
        try:
            self._set_job_fields(job_id, status="running", stage="running_backup", started_at=datetime.now())
            result = await asyncio.to_thread(backup_service.perform_backup, True)
            if not result:
                raise RuntimeError("Backup was skipped or disabled for this environment")
            self._set_job_fields(job_id, status="success", stage="completed", finished_at=datetime.now())
        except Exception as exc:
            logger.exception("Backup run job failed: job_id=%s", job_id)
            self._set_job_fields(
                job_id,
                status="failed",
                stage="failed",
                error=str(exc),
                finished_at=datetime.now(),
            )
        finally:
            self._clear_active_if_needed(job_id)


backup_run_runtime_service = BackupRunRuntimeService()
