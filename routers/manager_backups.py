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
    """
    List up to 100 configured Google Drive backup entries for a system-tenant owner/admin. These
    are platform database/media backups, not tenant exports; listing performs no restore.
    Unconfigured storage returns 503 and credential/provider listing failures return 502 with
    detail.error_code=backup_list_unavailable in the Manager error envelope.
    """
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
    """
    Start a manual platform backup in the API process and return 202 with job_id/status/stage.
    Requires a system-tenant owner/admin and production environment (otherwise 400). A known
    active backup or restore returns 409; startup failure returns 500. Poll
    /api/manager/backups/run/{job_id}; 202 is acceptance, not backup success. Job records and
    exclusion locks are process-local and do not survive restart or provide an HA-wide lock. No
    replay key is supported.
    """
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
    """
    Read a manual backup job from this API process's in-memory registry; requires a
    system-tenant owner/admin. Returns status/stage/timestamps and error, with success/failed
    terminal outcomes. Unknown jobs return 404, including after a process restart or on another
    worker/node. This endpoint neither starts nor retries a backup.
    """
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
    """
    Start restoration of a configured platform database or media backup and return 202 with a
    job ID. Requires a system-tenant owner/admin and BACKUP_RESTORE_ENABLED; normal operation
    returns 503 because restore is disabled. This can replace shared production data and belongs
    to the supervised [production-data
    procedure](https://github.com/mvnby/air-api/blob/main/docs/production-data-operations.md).
    Known active jobs return 409, an unlisted file 404 and unsupported kind 400. The job first
    creates a safety copy; completion/failure must be polled. State and exclusion locks are
    process-local, without an HA-wide lock or replay receipt.
    """
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
    """
    Read a restore job from this API process's in-memory registry; requires a system-tenant
    owner/admin. Includes stage, terminal success/failed, error and safety-copy path when
    available. Unknown jobs return 404, including after restart or when polling a different
    worker/node. Reading status does not enable, start or repeat restoration.
    """
    job = backup_restore_runtime_service.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Restore job not found")
    return ManagerRestoreJobStatusResponse(**job)
