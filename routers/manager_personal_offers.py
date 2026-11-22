from fastapi import APIRouter, Depends, Path, Query, Response
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.personal_offers import (
    ManagerPersonalOfferListResponse,
    ManagerPersonalOfferResponse,
    PersonalOfferDraftInput,
    PersonalOfferPublishInput,
    PersonalOfferUpdateInput,
    PersonalOfferVersionInput,
    PublicPersonalOfferResponse,
)
from core.database import get_session
from core.security import get_current_manager_tenant_scope
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    CREATE_MANAGER_PERSONAL_OFFER,
    GET_MANAGER_PERSONAL_OFFER,
    LIST_MANAGER_PERSONAL_OFFERS,
    PREVIEW_MANAGER_PERSONAL_OFFER,
    PUBLISH_MANAGER_PERSONAL_OFFER,
    REVOKE_MANAGER_PERSONAL_OFFER,
    UPDATE_MANAGER_PERSONAL_OFFER,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from services.personal_offer_service import PersonalOfferService


async def _disable_cache(response: Response) -> None:
    response.headers["Cache-Control"] = "private, no-store"


router = APIRouter(
    prefix="/api/manager/personal-offers",
    tags=["manager personal offers"],
    route_class=ManagerPermissionRoute,
    dependencies=[Depends(_disable_cache)],
)


@router.get("", response_model=ManagerPersonalOfferListResponse, operation_id=LIST_MANAGER_PERSONAL_OFFERS)
async def list_manager_personal_offers(
    order_id: int | None = Query(default=None, gt=0),
    limit: int = Query(default=20, ge=1, le=100),
    before_id: int | None = Query(default=None, gt=0),
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """List drafts newest-first in the selected storefront, optionally for a CRM order."""
    return await PersonalOfferService.list(session, scope, order_id=order_id, limit=limit, before_id=before_id)


@router.post("", status_code=201, response_model=ManagerPersonalOfferResponse, operation_id=CREATE_MANAGER_PERSONAL_OFFER)
async def create_manager_personal_offer(
    draft: PersonalOfferDraftInput,
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """Save an unpublished draft, optionally tied to an in-scope order in negotiation."""
    return await PersonalOfferService.create(session, scope, draft)


@router.get("/{offer_id}", response_model=ManagerPersonalOfferResponse, operation_id=GET_MANAGER_PERSONAL_OFFER)
async def get_manager_personal_offer(
    offer_id: int = Path(gt=0),
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """Read a draft and its current share link, if any."""
    return await PersonalOfferService.get(session, offer_id, scope)


@router.put("/{offer_id}", response_model=ManagerPersonalOfferResponse, operation_id=UPDATE_MANAGER_PERSONAL_OFFER)
async def update_manager_personal_offer(
    draft: PersonalOfferUpdateInput,
    offer_id: int = Path(gt=0),
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """Replace editable draft fields using the last-read version. The live link is untouched."""
    return await PersonalOfferService.update(session, offer_id, scope, draft)


@router.post("/{offer_id}/preview", response_model=PublicPersonalOfferResponse, operation_id=PREVIEW_MANAGER_PERSONAL_OFFER)
async def preview_manager_personal_offer(
    offer_id: int = Path(gt=0),
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """Render the saved draft using the same allowlist as the client-facing page."""
    return await PersonalOfferService.preview(session, offer_id, scope)


@router.post("/{offer_id}/publish", response_model=ManagerPersonalOfferResponse, operation_id=PUBLISH_MANAGER_PERSONAL_OFFER)
async def publish_manager_personal_offer(
    command: PersonalOfferPublishInput,
    offer_id: int = Path(gt=0),
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """Publish a fixed snapshot. Replay the same UUID and version to recover from a lost response."""
    return await PersonalOfferService.publish(session, offer_id, scope, command)


@router.post("/{offer_id}/revoke", response_model=ManagerPersonalOfferResponse, operation_id=REVOKE_MANAGER_PERSONAL_OFFER)
async def revoke_manager_personal_offer(
    command: PersonalOfferVersionInput,
    offer_id: int = Path(gt=0),
    session: AsyncSession = Depends(get_session),
    scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """Immediately make the active link unavailable while retaining the draft."""
    return await PersonalOfferService.revoke(session, offer_id, scope, command.expected_version)
