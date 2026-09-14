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
    return ManagerInstallationRateListResponse(
        items=await ManagerInstallationRateService.list_rates(
            session, tenant_scope
        )
    )


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
    return await ManagerInstallationRateService.update_rate(
        session,
        rate_id=rate_id,
        payload=payload,
        tenant_scope=tenant_scope,
    )
