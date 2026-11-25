"""Company tender settings and platform-controlled module access."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import (
    AuthenticatedIdentity, AuthenticatedUser, get_current_platform_identity, require_owner_access,
)
from routers import manager_operation_ids as operation_ids
from routers.manager_platform_companies import require_company_origin
from schemas_tender_search import (
    TenderModuleAccess, TenderModuleEntitlementUpdate, TenderModuleSettings, TenderModuleUpdate,
    TenderProfilePreview, TenderSearchProfile,
)
from services.tender_module_service import TenderModuleError, TenderModuleService

router = APIRouter(prefix="/api/manager", tags=["manager-tender-module"])


@router.get(
    "/tender-module", response_model=TenderModuleSettings,
    operation_id=operation_ids.GET_MANAGER_TENDER_MODULE,
)
async def get_manager_tender_module(
    session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_owner_access),
):
    """Read module access, enablement, and the selected company's search profiles."""
    return await TenderModuleService.get(session, auth.tenant_scope().tenant_id)


@router.put(
    "/tender-module", response_model=TenderModuleSettings,
    operation_id=operation_ids.UPDATE_MANAGER_TENDER_MODULE, dependencies=[Depends(require_company_origin)],
)
async def update_manager_tender_module(
    payload: TenderModuleUpdate, session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_owner_access),
):
    """Save versioned preferences for the selected company with active module access."""
    try:
        return await TenderModuleService.update(session, auth, payload)
    except TenderModuleError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.get(
    "/platform/companies/{tenant_id}/tender-module", response_model=TenderModuleAccess,
    operation_id=operation_ids.GET_PLATFORM_COMPANY_TENDER_MODULE,
)
async def get_platform_company_tender_module(
    tenant_id: int, session: AsyncSession = Depends(get_session),
    _: AuthenticatedIdentity = Depends(get_current_platform_identity),
):
    """Read the specified company's entitlement as the platform owner."""
    try:
        return await TenderModuleService.get_company_access(session, tenant_id)
    except TenderModuleError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.post(
    "/tender-module/profile-preview", response_model=TenderProfilePreview,
    operation_id=operation_ids.PREVIEW_MANAGER_TENDER_PROFILE, dependencies=[Depends(require_company_origin)],
)
async def preview_manager_tender_profile(
    payload: TenderSearchProfile, session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_owner_access),
):
    """Apply the draft filter to the most recent tenders in the selected storefront."""
    try:
        return await TenderModuleService.preview(session, auth, payload)
    except TenderModuleError as exc:
        raise HTTPException(exc.status_code, str(exc)) from exc


@router.put(
    "/platform/companies/{tenant_id}/tender-module", response_model=TenderModuleAccess,
    operation_id=operation_ids.UPDATE_PLATFORM_COMPANY_TENDER_MODULE, dependencies=[Depends(require_company_origin)],
)
async def update_platform_company_tender_module(
    tenant_id: int, payload: TenderModuleEntitlementUpdate, session: AsyncSession = Depends(get_session),
    actor: AuthenticatedIdentity = Depends(get_current_platform_identity),
):
    """Grant or revoke module access with a version check and an audit entry."""
    try:
        return await TenderModuleService.set_entitlement(session, tenant_id, actor, payload)
    except TenderModuleError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, str(exc)) from exc
