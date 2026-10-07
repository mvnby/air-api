from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    CREATE_MEDIA_PROCESSING_JOB,
    LIST_MEDIA_PROCESSING_JOBS,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    ManagerMediaProcessingJobCreatePayload,
    ManagerMediaProcessingJobListResponse,
    ManagerMediaProcessingJobResponse,
)
from services.media_processing_job_service import MediaProcessingJobService


router = APIRouter(
    prefix="/api/manager/media/processing-jobs",
    tags=["manager media"],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "",
    response_model=ManagerMediaProcessingJobListResponse,
    operation_id=LIST_MEDIA_PROCESSING_JOBS,
)
async def list_media_processing_jobs(
    status: str | None = Query(None),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _username: str = Depends(get_current_username),
):
    """
    Read up to 100 newest shared media-processing jobs, optionally filtered by status.
    meta.total is the returned row count, not the size of the full queue; there is no
    page/offset. Lease tokens are excluded from normal Manager serialization. This does not
    claim or retry jobs.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await MediaProcessingJobService.list_jobs(
        session=session,
        status=status,
        limit=limit,
    )


@router.post(
    "/{asset_id}",
    response_model=ManagerMediaProcessingJobResponse,
    operation_id=CREATE_MEDIA_PROCESSING_JOB,
)
async def create_media_processing_job(
    asset_id: int,
    payload: ManagerMediaProcessingJobCreatePayload,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Persist a new queued background_removal or upscale job for a library raster asset.
    Missing source returns 404; unsupported operation or SVG source returns 400. Lower
    priority values are claimed first. The response confirms enqueue, not processing success
    or publication; each POST creates another job and the original asset remains unchanged.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await MediaProcessingJobService.create_job(
            session=session,
            source_asset_id=asset_id,
            operation=payload.operation,
            provider=payload.provider,
            rembg_model=payload.rembg_model,
            options=payload.options,
            priority=payload.priority,
            created_by=username,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
