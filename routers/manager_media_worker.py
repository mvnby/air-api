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
    """
    Atomically claim the next queued job or reclaim an expired running attempt, ordered by
    priority then creation time and filtered by worker capabilities. Empty capabilities
    means no capability filter. Returns job=null when none can be claimed; a claim
    increments attempts and rotates lease_token. Keep the returned worker_id/token pair for
    renew/complete/fail; a later claim is a new attempt.

    Access and scope: the configured MEDIA_WORKER_TOKEN is required via Authorization:
    Bearer or X-Media-Worker-Token (the latter takes precedence). Missing/invalid token
    returns 401; an unconfigured server token returns 503. Manager JWT/cookies do not
    authorize this endpoint.
    """
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
    """
    Extend an unexpired running attempt owned by the supplied worker_id and lease_token.
    Unknown job returns 404; stale token, changed owner/status or expired lease returns 409.
    The expiry is set from renewal time, so repetition may extend it again. Renew before
    expiration; expired leases can be reclaimed by another worker.

    Access and scope: the configured MEDIA_WORKER_TOKEN is required via Authorization:
    Bearer or X-Media-Worker-Token (the latter takes precedence). Missing/invalid token
    returns 401; an unconfigured server token returns 503. Manager JWT/cookies do not
    authorize this endpoint.
    """
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
    """
    Complete an unexpired owned attempt from multipart processed-image bytes and create a
    result child library asset. worker_id and lease_token must match the running attempt;
    missing job/source returns 404, invalid/stale/expired lease or invalid result returns
    409, and more than 50 MB returns 413. Success clears the lease and marks the job
    successful; a repeat is rejected with 409, not replayed.

    Access and scope: the configured MEDIA_WORKER_TOKEN is required via Authorization:
    Bearer or X-Media-Worker-Token (the latter takes precedence). Missing/invalid token
    returns 401; an unconfigured server token returns 503. Manager JWT/cookies do not
    authorize this endpoint. See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
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
    """
    Mark an unexpired running attempt failed with the supplied error, truncated to 2000
    characters, and clear its lease. Unknown job returns 404; stale token, wrong owner or
    expired/finished attempt returns 409. Failed jobs are not automatically claimable;
    repetition after success of this command returns 409.

    Access and scope: the configured MEDIA_WORKER_TOKEN is required via Authorization:
    Bearer or X-Media-Worker-Token (the latter takes precedence). Missing/invalid token
    returns 401; an unconfigured server token returns 503. Manager JWT/cookies do not
    authorize this endpoint.
    """
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
