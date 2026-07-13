import secrets

from fastapi import APIRouter, Depends, File, Form, Header, HTTPException, Path, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from routers.manager_operation_ids import (
    CLAIM_MEDIA_WORKER_JOB,
    COMPLETE_MEDIA_WORKER_JOB,
    FAIL_MEDIA_WORKER_JOB,
    RENEW_MEDIA_WORKER_JOB,
)
from schemas import (
    ManagerMediaProcessingJobResponse,
    MediaWorkerClaimPayload,
    MediaWorkerClaimResponse,
    MediaWorkerFailPayload,
    MediaWorkerRenewPayload,
)
from services.media_processing_job_service import MediaProcessingJobService


router = APIRouter(prefix="/api/manager/media/worker", tags=["manager media worker"])
MAX_MEDIA_WORKER_RESULT_BYTES = 50 * 1024 * 1024


def _extract_bearer_token(authorization: str | None) -> str | None:
    if not authorization:
        return None
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    return token.strip()


async def require_media_worker_token(
    authorization: str | None = Header(None),
    x_media_worker_token: str | None = Header(None),
) -> None:
    configured = settings.MEDIA_WORKER_TOKEN.strip()
    if not configured:
        raise HTTPException(status_code=503, detail="Media worker token is not configured")
    provided = x_media_worker_token or _extract_bearer_token(authorization)
    if provided is None or not secrets.compare_digest(provided, configured):
        raise HTTPException(status_code=401, detail="Invalid media worker token")


@router.post(
    "/jobs/claim",
    response_model=MediaWorkerClaimResponse,
    operation_id=CLAIM_MEDIA_WORKER_JOB,
)
async def claim_media_worker_job(
    payload: MediaWorkerClaimPayload,
    session: AsyncSession = Depends(get_session),
    _token: None = Depends(require_media_worker_token),
):
    job = await MediaProcessingJobService.claim_next_job(
        session=session,
        worker_id=payload.worker_id,
        capabilities=payload.capabilities,
        lease_seconds=payload.lease_seconds,
    )
    return {"job": job}


@router.post(
    "/jobs/{job_id}/renew",
    response_model=ManagerMediaProcessingJobResponse,
    operation_id=RENEW_MEDIA_WORKER_JOB,
)
async def renew_media_worker_job(
    payload: MediaWorkerRenewPayload,
    job_id: str = Path(..., min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
    _token: None = Depends(require_media_worker_token),
):
    try:
        return await MediaProcessingJobService.renew_lease(
            session=session,
            job_id=job_id,
            worker_id=payload.worker_id,
            lease_token=payload.lease_token,
            lease_seconds=payload.lease_seconds,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/jobs/{job_id}/complete",
    response_model=ManagerMediaProcessingJobResponse,
    operation_id=COMPLETE_MEDIA_WORKER_JOB,
)
async def complete_media_worker_job(
    job_id: str = Path(..., min_length=1, max_length=64),
    worker_id: str = Form(..., min_length=1, max_length=128),
    lease_token: str = Form(..., min_length=32, max_length=256),
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    _token: None = Depends(require_media_worker_token),
):
    try:
        content = await file.read(MAX_MEDIA_WORKER_RESULT_BYTES + 1)
        if len(content) > MAX_MEDIA_WORKER_RESULT_BYTES:
            raise HTTPException(status_code=413, detail="Processed image file is too large")
        return await MediaProcessingJobService.complete_job(
            session=session,
            job_id=job_id,
            worker_id=worker_id,
            lease_token=lease_token,
            content=content,
            filename=(file.filename or "")[:255] or None,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/jobs/{job_id}/fail",
    response_model=ManagerMediaProcessingJobResponse,
    operation_id=FAIL_MEDIA_WORKER_JOB,
)
async def fail_media_worker_job(
    payload: MediaWorkerFailPayload,
    job_id: str = Path(..., min_length=1, max_length=64),
    session: AsyncSession = Depends(get_session),
    _token: None = Depends(require_media_worker_token),
):
    try:
        return await MediaProcessingJobService.fail_job(
            session=session,
            job_id=job_id,
            worker_id=payload.worker_id,
            lease_token=payload.lease_token,
            error=payload.error,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
