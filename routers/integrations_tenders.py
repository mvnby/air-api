"""Dedicated server-only native tender intake."""

import logging
import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.database import get_session
from schemas_belzakupki_intake import NativeOpportunity, TenderLeadPushResult
from services.belzakupki_lead_push_service import BelzakupkiLeadPushService, LeadPushScopeDenied, LeadPushUnavailable

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/integrations/tenders", tags=["integrations-tenders"])
bearer = HTTPBearer(auto_error=False)


def require_lead_push_key(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)) -> None:
    try:
        BelzakupkiLeadPushService.check_configuration()
    except LeadPushUnavailable:
        raise HTTPException(503, {"code": "tender_intake_unavailable", "message": "Tender lead push is unavailable"}) from None
    supplied = credentials.credentials if credentials and credentials.scheme.lower() == "bearer" else ""
    if not secrets.compare_digest(supplied.encode(), settings.BELZAKUPKI_LEAD_PUSH_API_KEY.encode()):
        logger.warning("BELZAKUPKI_LEAD_PUSH denied=authentication")
        raise HTTPException(401, {"code": "invalid_integration_credentials", "message": "Invalid integration credentials"}, headers={"WWW-Authenticate": "Bearer"})


@router.post("/leads", response_model=TenderLeadPushResult, operation_id="push_tender_lead",
             dependencies=[Depends(require_lead_push_key)])
async def push_tender_lead(opportunity: NativeOpportunity, session: AsyncSession = Depends(get_session)):
    """Accept one native opportunity using the dedicated Bearer key and server-owned destination.

    Activation and writable-primary controls fail closed. Replays deduplicate by source and
    external tender ID; source updates preserve staff workflow and reviewed enrichment.
    Creation follows the existing confirmed/eligible/deadline rules. Older updates cannot
    replace newer source state. Push does not advance the shared pull cursor or timestamp.
    The validated native model is limited to 64 KiB; IDs are producer-owned and timestamps
    are timezone-aware. Returns a nullable order ID and created/updated/unchanged/skipped.
    Configured intake rejects missing/wrong keys with 401, invalid destination with 403,
    disabled/unwritable intake with 503 and malformed payload with 422. The outer HA fence
    may return its own 503 before routing.
    No source HTTP request, customer qualification or downstream business action is performed.

    See [intake contract](https://github.com/mvnby/air-api/blob/main/docs/belzakupki-intake.md#direct-push-intake-849-first-release-slice).
    """
    try:
        return await BelzakupkiLeadPushService.push(session, opportunity)
    except LeadPushScopeDenied:
        logger.warning("BELZAKUPKI_LEAD_PUSH denied=scope")
        raise HTTPException(403, {"code": "tender_intake_scope_denied", "message": "Tender lead destination is unavailable"}) from None
    except (LeadPushUnavailable, DBAPIError):
        logger.warning("BELZAKUPKI_LEAD_PUSH failed=unavailable")
        raise HTTPException(503, {"code": "tender_intake_unavailable", "message": "Tender lead push is unavailable"}) from None
