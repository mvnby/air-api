"""Manager multi-split preview and proposal actions."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.multi_split import (
    ManagerMultiSplitPreviewResponse,
    ManagerMultiSplitSavePayload,
    MultiSplitOptionsResponse,
    MultiSplitPreviewRequest,
)
from core.database import get_session
from core.security import get_current_manager_tenant_scope
from models.tenancy import TenantScope
from routers.manager_operation_ids import LIST_MANAGER_MULTI_SPLIT_OPTIONS, PREVIEW_MANAGER_MULTI_SPLIT, SAVE_MANAGER_MULTI_SPLIT_PROPOSAL
from routers.manager_permission_policy import ManagerPermissionRoute
from services.multi_split_configuration_service import MultiSplitConfigurationService, MultiSplitSelectionError
from services.multi_split_proposal_service import MultiSplitProposalService, MultiSplitStalePreviewError
from schemas import ManagerOrderDetailResponse

router = APIRouter(prefix="/api/manager/multi-split", tags=["manager multi-split"], route_class=ManagerPermissionRoute)


@router.get("/options", response_model=MultiSplitOptionsResponse, operation_id=LIST_MANAGER_MULTI_SPLIT_OPTIONS)
async def list_manager_multi_split_options(
    kind: Literal["outdoor_unit", "indoor_unit"],
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read paginated eligible outdoor or indoor multi-split units for the selected storefront;
    limit is 1–100. This option list does not certify that arbitrary units are compatible or
    create an order/proposal.

    Access and scope: Manager access is required; data is restricted to the authenticated
    tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await MultiSplitConfigurationService.list_options(
        session, tenant_scope=tenant_scope, kind=kind, page=page, limit=limit,
    )


@router.post("/preview", response_model=ManagerMultiSplitPreviewResponse, operation_id=PREVIEW_MANAGER_MULTI_SPLIT)
async def preview_manager_multi_split(
    payload: MultiSplitPreviewRequest,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Calculate a multi-split configuration and compatibility status from rooms and selected
    units, using current catalog/supply data. Invalid selection returns 422. Compatibility
    may be unverified when no confirmed profile exists; preview is not a saved order. Demo
    scope omits commercial details; accepted components/status must be sent back when
    saving.

    Access and scope: Manager access is required; data is restricted to the authenticated
    tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        preview = await MultiSplitConfigurationService.preview(
            session, tenant_scope=tenant_scope, request=payload,
        )
    except MultiSplitSelectionError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return preview.manager_response(show_commercial=not tenant_scope.demo_read_only)


@router.post(
    "/orders/{order_id}/proposals",
    response_model=ManagerOrderDetailResponse,
    operation_id=SAVE_MANAGER_MULTI_SPLIT_PROPOSAL,
)
async def save_manager_multi_split_proposal(
    order_id: int,
    payload: ManagerMultiSplitSavePayload,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Save a recalculated multi-split configuration as a new draft alternative or an empty
    existing draft in a scoped negotiation order. Changed components/status returns 409 and
    requires preview again; incompatible or invalid/lifecycle selections return 400. Saves
    component/price snapshots, profile provenance and financials together. Each
    new-alternative POST may create another proposal; no idempotency receipt exists.

    Access and scope: Manager access is required; data is restricted to the authenticated
    tenant and selected storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await MultiSplitProposalService.save(
            session, tenant_scope=tenant_scope, order_id=order_id, payload=payload,
        )
    except MultiSplitStalePreviewError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
