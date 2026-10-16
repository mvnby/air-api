"""Company/site visibility for platform and company owners."""

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.manager_platform_companies import CompanySitesResponse, PlatformCompanyListResponse, PlatformCompanyResponse, PlatformCompanyUpdate
from core.database import get_session
from core.security import AuthenticatedIdentity, AuthenticatedUser, get_current_platform_identity, require_owner_access
from routers.manager_profile import require_account_origin
from routers.manager_operation_ids import (
    MANAGER_LIST_PLATFORM_COMPANIES, MANAGER_UPDATE_PLATFORM_COMPANY,
    MANAGER_LIST_COMPANY_SITES,
)
from services.platform_companies_service import PlatformCompaniesService, PlatformCompanyError

router = APIRouter(prefix="/api/manager", tags=["manager-platform-companies"])


def require_company_origin(request: Request):
    require_account_origin(request, header="X-Kitlane-Team")


@router.get("/platform/companies", response_model=PlatformCompanyListResponse, operation_id=MANAGER_LIST_PLATFORM_COMPANIES)
async def list_platform_companies(
    page: int = Query(1, ge=1), limit: int = Query(50, ge=1, le=100), search: str | None = Query(None, max_length=200),
    session: AsyncSession = Depends(get_session), actor: AuthenticatedIdentity = Depends(get_current_platform_identity),
):
    """List every company, owners, live staff counts and all sites/domains for the platform owner.

    Includes disabled/demo companies and unpublished sites; never exposes credentials.
    Independent of selected company headers. Company owners/admins receive 403.
    Page-based pagination is bounded to 100 companies; search matches name or slug.
    """
    return await PlatformCompaniesService.list(session, page=page, limit=limit, search=search)


@router.patch("/platform/companies/{tenant_id}", response_model=PlatformCompanyResponse,
              operation_id=MANAGER_UPDATE_PLATFORM_COMPANY, dependencies=[Depends(require_company_origin)])
async def update_platform_company(
    tenant_id: int, payload: PlatformCompanyUpdate, session: AsyncSession = Depends(get_session),
    actor: AuthenticatedIdentity = Depends(get_current_platform_identity),
):
    """Change a company name or active/disabled status as the live platform owner; audit atomically.

    Requires X-Kitlane-Team: 1, approved origin and exact expected_updated_at. Stale state
    returns 409, missing company 404; the canonical system company cannot be disabled.
    Disabling blocks company access on fresh requests; it does not delete business data,
    change catalog grants, provision sites or edit DNS. Re-read before retrying a conflict.
    """
    try:
        return await PlatformCompaniesService.update(session, tenant_id=tenant_id, payload=payload, actor=actor)
    except PlatformCompanyError as exc:
        await session.rollback()
        raise HTTPException(exc.status_code, detail={"code": exc.code, "message": str(exc)}) from exc


@router.get("/company/sites", response_model=CompanySitesResponse, operation_id=MANAGER_LIST_COMPANY_SITES)
async def list_company_sites(
    page: int = Query(1, ge=1), limit: int = Query(100, ge=1, le=100),
    session: AsyncSession = Depends(get_session), auth: AuthenticatedUser = Depends(require_owner_access),
):
    """Show all sites and domain states in the selected company to its owner/admin.

    Includes draft and disabled sites for visibility. This read-only endpoint cannot
    provision a site, publish it or alter a domain. No other company's sites are returned.
    Page-based pagination returns at most 100 sites.
    """
    return await PlatformCompaniesService.own_sites(session, tenant_id=auth.tenant_scope().tenant_id, page=page, limit=limit)
