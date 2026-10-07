from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from core.security import get_current_username
from schemas import (
    WebRebuildCompletePayload,
    WebRebuildStatusResponse,
    WebRebuildTriggerResponse,
)
from services.catalog_revision_service import CatalogRevisionService
from services.system_service import system_service
from core.logger import logger

router = APIRouter(prefix="/api/system", tags=["system"])


@router.get("/rebuild-web/status", response_model=WebRebuildStatusResponse)
async def get_rebuild_web_status(
    username: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    """
    Read global catalog revision and storefront synchronization acknowledgement state for an
    authenticated Manager. This is platform-wide catalog publication state, not a per-tenant job
    or a deployment health check. Reading does not dispatch a workflow; the recorded
    acknowledgement alone does not verify current storefront availability.
    """
    logger.debug("User %s checked web rebuild status.", username)
    return await CatalogRevisionService.get_static_rebuild_status(session)


@router.post("/rebuild-web", response_model=WebRebuildTriggerResponse)
async def trigger_rebuild_web(
    username: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    """
    Dispatch the standalone storefront's catalog synchronization workflow for the current global
    revision, then record that revision as requested. Requires Manager access. A missing GitHub
    integration token returns 503; dispatch failure returns 500. A successful response
    acknowledges dispatch, not completed synchronization; read /api/system/rebuild-web/status
    afterward. No Idempotency-Key receipt prevents repeated workflow dispatches.
    """
    status = await CatalogRevisionService.get_static_rebuild_status(session)
    current_revision = int(status["current_revision"])

    logger.info(
        "User %s triggered a web site rebuild for catalog revision %s.",
        username,
        current_revision,
    )

    result = await system_service.trigger_web_rebuild(catalog_revision=current_revision)
    
    if not result["success"]:
        # Handle specific known errors
        if result["error"] == "GITHUB_TOKEN_MISSING":
            raise HTTPException(
                status_code=503, 
                detail="GitHub integration not configured on server (.env missing GITHUB_TOKEN)"
            )

        details = result.get("details") or result.get("status_code") or result.get("error")
        raise HTTPException(
            status_code=500, 
            detail=f"Failed to trigger rebuild: {result.get('error')}. Details: {details}"
        )

    status = await CatalogRevisionService.mark_static_rebuild_requested(
        session,
        current_revision,
    )
    await session.commit()

    return {
        **status,
        "message": "Storefront catalog synchronization started.",
    }


@router.post("/rebuild-web/complete", response_model=WebRebuildStatusResponse)
async def complete_rebuild_web(
    payload: WebRebuildCompletePayload,
    x_web_rebuild_token: str | None = Header(default=None, alias="X-Web-Rebuild-Token"),
    session: AsyncSession = Depends(get_session),
):
    """
    Record the standalone storefront's catalog synchronization callback using the shared
    X-Web-Rebuild-Token header, not a Manager JWT or an HMAC signature. Missing server token
    configuration returns 503; invalid token returns 403. Revision zero resolves to the current
    revision. Success stores the supplied published revision/timestamp and clears the error;
    failure stores requested revision/error. This writes global state, has no replay receipt or
    monotonic-revision guard, and repeated or out-of-order callbacks can replace recorded state.
    It does not itself verify the storefront.
    """
    if not settings.WEB_REBUILD_CALLBACK_TOKEN:
        raise HTTPException(status_code=503, detail="Web rebuild callback token is not configured")
    if x_web_rebuild_token != settings.WEB_REBUILD_CALLBACK_TOKEN:
        raise HTTPException(status_code=403, detail="Invalid web rebuild callback token")

    catalog_revision = max(0, int(payload.catalog_revision))
    if catalog_revision == 0:
        current = await CatalogRevisionService.get_current(session)
        catalog_revision = int(current["revision"])

    status_value = str(payload.status or "success").strip().lower()
    if status_value == "success":
        status = await CatalogRevisionService.mark_static_rebuild_completed(
            session,
            catalog_revision,
        )
    else:
        status = await CatalogRevisionService.mark_static_rebuild_failed(
            session,
            catalog_revision,
            payload.error or "GitHub Actions rebuild failed",
        )
    await session.commit()
    return status
