from typing import Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    GET_MANAGER_INSTALLERS,
    CREATE_MANAGER_INSTALLER,
    UPDATE_MANAGER_INSTALLER,
    SEARCH_MANAGER_INSTALLERS,
)
from schemas import (
    ManagerInstallerCreatePayload,
    ManagerInstallerUpdatePayload,
    ManagerInstallerResponse,
    ManagerInstallerListResponse,
)
from services.installer_service import ManagerInstallerService

router = APIRouter(prefix="/api/manager/installers", tags=["manager-installers"])


@router.get(
    "",
    response_model=ManagerInstallerListResponse,
    operation_id=GET_MANAGER_INSTALLERS,
)
async def list_installers(
    page: int = Query(1, ge=1),
    limit: int = Query(100, ge=1, le=500),
    search: Optional[str] = Query(None),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read a paginated installer/staff projection for the tenant, optionally filtering by
    search text. page starts at 1; this route currently accepts limit 1–500, default 100.
    Membership status determines tenant activity independently of the global staff identity.

    Access and scope: Manager access is required; installer visibility follows staff
    membership in the authenticated tenant. The system tenant also sees unmapped legacy
    installers. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await ManagerInstallerService.get_all(
        session=session,
        page=page,
        limit=limit,
        search=search,
        tenant_scope=tenant_scope,
    )


@router.post(
    "",
    response_model=ManagerInstallerResponse,
    operation_id=CREATE_MANAGER_INSTALLER,
)
async def create_installer(
    payload: ManagerInstallerCreatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Create an installer and ensure its linked staff identity and membership in the
    authenticated tenant. Creation errors are returned as 400. This has staff-account side
    effects and no idempotency receipt, so repeated calls are not guaranteed to reuse a
    prior installer.

    Access and scope: Manager access is required; installer visibility follows staff
    membership in the authenticated tenant. The system tenant also sees unmapped legacy
    installers. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await ManagerInstallerService.create(
            session=session,
            payload=payload,
            tenant_scope=tenant_scope,
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get(
    "/search",
    response_model=ManagerInstallerListResponse,
    operation_id=SEARCH_MANAGER_INSTALLERS,
)
async def search_installers(
    q: str = Query(..., min_length=1, description="Search term for installer name"),
    limit: int = Query(50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Search active tenant installers by name for autocomplete. q must be nonempty and limit
    is 1–100, default 50; this is a bounded suggestion list without page navigation. No
    installer/staff membership is created.

    Access and scope: Manager access is required; installer visibility follows staff
    membership in the authenticated tenant. The system tenant also sees unmapped legacy
    installers. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await ManagerInstallerService.search(
        session=session,
        q=q,
        limit=limit,
        tenant_scope=tenant_scope,
    )


@router.put(
    "/{installer_id}",
    response_model=ManagerInstallerResponse,
    operation_id=UPDATE_MANAGER_INSTALLER,
)
async def update_installer(
    installer_id: int,
    payload: ManagerInstallerUpdatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Update submitted non-null installer identity fields and/or the current tenant
    membership’s activity. Missing/inaccessible installer returns 404. Partners cannot edit
    shared identity fields when the staff user has multiple memberships; this service
    rejection is not converted to a dedicated client error by this route. Omitted/null
    fields are ignored, including telegram_id; membership changes also recompute aggregate
    staff activity. No expected-version guard is used.

    Access and scope: Manager access is required; installer visibility follows staff
    membership in the authenticated tenant. The system tenant also sees unmapped legacy
    installers. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    installer = await ManagerInstallerService.update(
        session=session,
        installer_id=installer_id,
        payload=payload,
        tenant_scope=tenant_scope,
    )
    if not installer:
        raise HTTPException(status_code=404, detail="Монтажник не найден")
    return installer
