import asyncio
import os
import shutil
import tempfile
from datetime import datetime
from threading import Lock
from typing import Any, Dict, Optional
from uuid import uuid4

from core.logger import logger
from services.backup_service import BACKUP_DIR, backup_service


class RestoreConflictError(Exception):
    pass


class BackupNotFoundError(Exception):
    pass


class UnsupportedBackupTypeError(Exception):
    pass


class BackupRestoreRuntimeService:
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

    async def start_restore(self, file_id: str) -> Dict[str, Any]:
        backups = await asyncio.to_thread(backup_service.list_backups, 200)
        backup_item = next((item for item in backups if item.get("id") == file_id), None)
        if not backup_item:
            raise BackupNotFoundError("Backup not found")
        if backup_item.get("kind") != "db":
            raise UnsupportedBackupTypeError("Only DB backups are supported in DR v1")

        with self._lock:
            if self._active_job_id:
                active = self._get_job_unsafe(self._active_job_id)
                if active and active.get("status") in {"queued", "running"}:
                    raise RestoreConflictError("Another restore job is already running")

            job_id = uuid4().hex
            now = datetime.now()
            job_payload: Dict[str, Any] = {
                "job_id": job_id,
                "file_id": file_id,
                "file_name": backup_item.get("name"),
                "kind": backup_item.get("kind"),
                "status": "queued",
                "stage": "queued",
                "error": None,
                "started_at": None,
                "finished_at": None,
                "updated_at": now,
                "safety_dump_path": None,
            }
            self._jobs[job_id] = job_payload
            self._active_job_id = job_id

        asyncio.create_task(self._run_restore_job(job_id))
        return self.get_job(job_id) or job_payload

    async def _run_restore_job(self, job_id: str):
        job = self.get_job(job_id)
        if not job:
            return

        job_file_name = job.get("file_name") or f"{job_id}.sql"
        temp_dir = tempfile.mkdtemp(prefix=f"restore_{job_id}_", dir=BACKUP_DIR)
        downloaded_path = os.path.join(temp_dir, job_file_name)
        sql_path = downloaded_path

        try:
            self._set_job_fields(job_id, status="running", stage="creating_safety_dump", started_at=datetime.now())
            safety_dump_path = await asyncio.to_thread(
                backup_service.create_dump,
                f"safety_pre_restore_{backup_service.db_name}",
            )
            self._set_job_fields(job_id, safety_dump_path=safety_dump_path)

            self._set_job_fields(job_id, stage="downloading_backup")
            await asyncio.to_thread(backup_service.download_backup_file, job["file_id"], downloaded_path)

            if downloaded_path.lower().endswith(".gz"):
                self._set_job_fields(job_id, stage="decompressing_backup")
                sql_path = downloaded_path[:-3]
                await asyncio.to_thread(backup_service.decompress_gzip_file, downloaded_path, sql_path)

            self._set_job_fields(job_id, stage="restoring_database")
            await backup_service.restore_from_file_async(sql_path)

            self._set_job_fields(job_id, status="success", stage="completed", finished_at=datetime.now())
        except Exception as exc:
            logger.exception("Restore job failed: job_id=%s", job_id)
            self._set_job_fields(
                job_id,
                status="failed",
                stage="failed",
                error=str(exc),
                finished_at=datetime.now(),
            )
        finally:
            shutil.rmtree(temp_dir, ignore_errors=True)
            self._clear_active_if_needed(job_id)


backup_restore_runtime_service = BackupRestoreRuntimeService()
