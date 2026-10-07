"""Platform Manager API for the public checkout installation-rate dictionary."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    LIST_MANAGER_INSTALLATION_RATES,
    UPDATE_MANAGER_INSTALLATION_RATE,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas_manager_installation_rates import (
    ManagerInstallationRateListResponse,
    ManagerInstallationRateResponse,
    ManagerInstallationRateUpdatePayload,
)
from services.manager_installation_rate_service import ManagerInstallationRateService


router = APIRouter(
    prefix="/api/manager/installation-rates",
    tags=["manager/installation-rates"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "",
    response_model=ManagerInstallationRateListResponse,
    operation_id=LIST_MANAGER_INSTALLATION_RATES,
)
async def list_manager_installation_rates(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read the tenant’s legacy installation-rate projection before price-book publication.
    Once a book is published, items is empty and published_price_book_revision identifies
    the active replacement. This does not delete rates or accepted historical calculations.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await ManagerInstallationRateService.list_response(session, tenant_scope)


@router.put(
    "/{rate_id}",
    response_model=ManagerInstallationRateResponse,
    operation_id=UPDATE_MANAGER_INSTALLATION_RATE,
)
async def update_manager_installation_rate(
    rate_id: int,
    payload: ManagerInstallationRateUpdatePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Save submitted legacy rate fields under the tenant publication lock.
    Missing/out-of-scope rate returns 404; after book publication the route returns 409
    installation_rates_retired. This edits the pre-publication rate dictionary without
    publishing a price book or rewriting accepted estimates.

    Access and scope: Manager access is required; service catalog data belongs to the
    authenticated tenant, independently of storefront. The system tenant also reads legacy
    rows with NULL tenant ownership. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [installation estimate
    contract](https://github.com/mvnby/air-api/blob/main/docs/installation-estimate-contract.md).
    """
    return await ManagerInstallationRateService.update_rate(
        session,
        rate_id=rate_id,
        payload=payload,
        tenant_scope=tenant_scope,
    )
