import logging

from fastapi import APIRouter, Depends, HTTPException, status
from starlette.concurrency import run_in_threadpool

from core.config import settings
from core.manager_api_errors import manager_http_error
from core.security import get_current_owner_username
from routers.manager_operation_ids import (
    GET_MANAGER_BACKUP_RUN_STATUS,
    GET_MANAGER_BACKUP_RESTORE_STATUS,
    LIST_MANAGER_BACKUPS,
    START_MANAGER_BACKUP_RUN,
    START_MANAGER_BACKUP_RESTORE,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    ManagerBackupListResponse,
    ManagerBackupRunStartResponse,
    ManagerBackupRunStatusResponse,
    ManagerRestoreJobStartResponse,
    ManagerRestoreJobStatusResponse,
)
from services.backup_run_runtime_service import (
    BackupRunConflictError,
    backup_run_runtime_service,
)
from services.backup_service import BackupConfigurationError, backup_service
from services.google_oauth_credentials import GoogleCredentialsError, GoogleDriveListError
from services.backup_restore_runtime_service import (
    BackupNotFoundError,
    RestoreConflictError,
    UnsupportedBackupTypeError,
    backup_restore_runtime_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/api/manager/backups",
    tags=["manager/backups"],
    dependencies=[Depends(get_current_owner_username)],
    route_class=ManagerPermissionRoute,
)
BACKUP_LIST_UNAVAILABLE = "backup_list_unavailable"
BACKUP_LIST_UNAVAILABLE_MESSAGE = "Список резервных копий временно недоступен"


@router.get("", response_model=ManagerBackupListResponse, operation_id=LIST_MANAGER_BACKUPS)
async def list_manager_backups():
    try:
        items = await run_in_threadpool(lambda: backup_service.list_backups(limit=100))
    except BackupConfigurationError as exc:
        logger.error("Backup list is unavailable because backup storage is not configured")
        raise manager_http_error(
            status_code=503,
            endpoint=LIST_MANAGER_BACKUPS,
            error_code=BACKUP_LIST_UNAVAILABLE,
            message=BACKUP_LIST_UNAVAILABLE_MESSAGE,
        ) from exc
    except (GoogleCredentialsError, GoogleDriveListError) as exc:
        logger.warning("Backup list is unavailable error_type=%s", type(exc).__name__)
        raise manager_http_error(
            status_code=502,
            endpoint=LIST_MANAGER_BACKUPS,
            error_code=BACKUP_LIST_UNAVAILABLE,
            message=BACKUP_LIST_UNAVAILABLE_MESSAGE,
        ) from exc
    return ManagerBackupListResponse(items=items)


@router.post(
    "/run",
    response_model=ManagerBackupRunStartResponse,
    operation_id=START_MANAGER_BACKUP_RUN,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_manager_backup_run():
    if not settings.is_production:
        raise HTTPException(
            status_code=400,
            detail=f"Manual backup is enabled only in production (current: {settings.ENVIRONMENT})",
        )

    if backup_restore_runtime_service.has_active_job():
        raise HTTPException(status_code=409, detail="Restore job is running. Wait until it finishes.")

    try:
        job = await backup_run_runtime_service.start_backup()
    except BackupRunConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to start manual backup job")
        raise HTTPException(status_code=500, detail="Failed to start backup job") from exc

    return ManagerBackupRunStartResponse(
        job_id=job["job_id"],
        status=job["status"],
        stage=job["stage"],
    )


@router.get(
    "/run/{job_id}",
    response_model=ManagerBackupRunStatusResponse,
    operation_id=GET_MANAGER_BACKUP_RUN_STATUS,
)
async def get_manager_backup_run_status(job_id: str):
    job = backup_run_runtime_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Backup job not found")
    return ManagerBackupRunStatusResponse(**job)


@router.post(
    "/restore/{file_id}",
    response_model=ManagerRestoreJobStartResponse,
    operation_id=START_MANAGER_BACKUP_RESTORE,
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_manager_backup_restore(file_id: str):
    if not settings.BACKUP_RESTORE_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "Restore is disabled during normal API operation. "
                "Use the supervised maintenance restore runbook."
            ),
        )

    if backup_run_runtime_service.has_active_job():
        raise HTTPException(status_code=409, detail="Backup job is running. Wait until it finishes.")

    try:
        job = await backup_restore_runtime_service.start_restore(file_id)
    except RestoreConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except BackupNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except UnsupportedBackupTypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("Failed to start restore job for file_id=%s", file_id)
        raise HTTPException(status_code=500, detail="Failed to start restore job") from exc

    return ManagerRestoreJobStartResponse(
        job_id=job["job_id"],
        status=job["status"],
        stage=job["stage"],
    )


@router.get(
    "/restore/{job_id}",
    response_model=ManagerRestoreJobStatusResponse,
    operation_id=GET_MANAGER_BACKUP_RESTORE_STATUS,
)
async def get_manager_backup_restore_status(job_id: str):
    job = backup_restore_runtime_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Restore job not found")
    return ManagerRestoreJobStatusResponse(**job)
