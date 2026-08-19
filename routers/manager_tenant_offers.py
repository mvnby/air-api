from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.tenant_offers import (
    ManagerTenantAuditEventListResponse,
    ManagerTenantOfferListResponse,
    ManagerTenantOfferResponse,
    ManagerTenantOfferUpdate,
    ManagerTenantOfferUpsert,
    POSTGRESQL_INTEGER_MAX,
)
from core.database import get_session
from core.security import AuthenticatedUser, require_manager_access
from routers.manager_operation_ids import (
    GET_MANAGER_TENANT_OFFER,
    LIST_MANAGER_TENANT_AUDIT_EVENTS,
    LIST_MANAGER_TENANT_OFFERS,
    UPDATE_MANAGER_TENANT_OFFER,
    UPSERT_MANAGER_TENANT_OFFER,
)
from services.tenant_offer_service import TenantOfferService
from routers.manager_permission_policy import ManagerPermissionRoute


router = APIRouter(
    prefix="/api/manager/tenant-offers",
    tags=["manager tenant offers"],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/audit",
    response_model=ManagerTenantAuditEventListResponse,
    operation_id=LIST_MANAGER_TENANT_AUDIT_EVENTS,
)
async def list_manager_tenant_audit_events(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    return await TenantOfferService.list_audit_events(
        session,
        tenant_scope=auth.tenant_scope(),
        offset=offset,
        limit=limit,
    )


@router.get(
    "",
    response_model=ManagerTenantOfferListResponse,
    operation_id=LIST_MANAGER_TENANT_OFFERS,
)
async def list_manager_tenant_offers(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=50, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    return await TenantOfferService.list_offers(
        session,
        tenant_scope=auth.tenant_scope(),
        offset=offset,
        limit=limit,
    )


@router.post(
    "",
    response_model=ManagerTenantOfferResponse,
    operation_id=UPSERT_MANAGER_TENANT_OFFER,
)
async def upsert_manager_tenant_offer(
    payload: ManagerTenantOfferUpsert,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    return await TenantOfferService.upsert_offer(
        session,
        payload=payload.model_dump(),
        tenant_scope=auth.tenant_scope(),
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
    )


@router.get(
    "/{offer_id}",
    response_model=ManagerTenantOfferResponse,
    operation_id=GET_MANAGER_TENANT_OFFER,
)
async def get_manager_tenant_offer(
    offer_id: Annotated[int, Path(ge=1, le=POSTGRESQL_INTEGER_MAX)],
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    return await TenantOfferService.get_offer(
        session,
        offer_id=offer_id,
        tenant_scope=auth.tenant_scope(),
    )


@router.patch(
    "/{offer_id}",
    response_model=ManagerTenantOfferResponse,
    operation_id=UPDATE_MANAGER_TENANT_OFFER,
)
async def update_manager_tenant_offer(
    offer_id: Annotated[int, Path(ge=1, le=POSTGRESQL_INTEGER_MAX)],
    payload: ManagerTenantOfferUpdate,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
):
    return await TenantOfferService.update_offer(
        session,
        offer_id=offer_id,
        payload=payload.model_dump(exclude_unset=True),
        tenant_scope=auth.tenant_scope(),
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
    )
