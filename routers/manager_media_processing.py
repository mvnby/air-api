from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    CREATE_MEDIA_PROCESSING_JOB,
    LIST_MEDIA_PROCESSING_JOBS,
)
from schemas import (
    ManagerMediaProcessingJobCreatePayload,
    ManagerMediaProcessingJobListResponse,
    ManagerMediaProcessingJobResponse,
)
from services.media_processing_job_service import MediaProcessingJobService


router = APIRouter(prefix="/api/manager/media/processing-jobs", tags=["manager media"])


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
