from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_manager_tenant_scope, get_current_username
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    CREATE_MANAGER_WARRANTY_POLICY,
    DECIDE_MANAGER_WARRANTY_COVERAGE,
    LIST_MANAGER_EQUIPMENT_WARRANTY_COVERAGES,
    LIST_MANAGER_WARRANTY_POLICIES,
    PATCH_MANAGER_WARRANTY_POLICY,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    ManagerEquipmentWarrantyCoverageResponse,
    ManagerWarrantyDecisionPayload,
    ManagerWarrantyPolicyListResponse,
    ManagerWarrantyPolicyPayload,
    ManagerWarrantyPolicyResponse,
)
from services.warranty_coverage_service import WarrantyCoverageService
from services.warranty_service import WarrantyService


router = APIRouter(
    prefix="/api/manager",
    tags=["manager-warranties"],
    route_class=ManagerPermissionRoute,
)


@router.get("/warranty-policies", response_model=ManagerWarrantyPolicyListResponse, operation_id=LIST_MANAGER_WARRANTY_POLICIES)
async def list_manager_warranty_policies(
    supplier_id: int | None = Query(None),
    brand_id: int | None = Query(None),
    series_id: int | None = Query(None),
    product_id: int | None = Query(None),
    include_inactive: bool = Query(False),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    """
    Read shared warranty policy definitions filtered by supplier, brand, series or product;
    inactive policies are excluded by default. This list is unpaginated. Policies are
    definitions for coverage selection, not the live warranty status of a customer equipment
    record.

    Access and scope: Manager access is required; these definitions are shared across
    tenants. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [warranty policy
    contract](https://github.com/mvnby/air-api/blob/main/docs/warranty-policies.md).
    """
    return {
        "items": await WarrantyService.list_policies(
            session,
            supplier_id=supplier_id,
            brand_id=brand_id,
            series_id=series_id,
            product_id=product_id,
            include_inactive=include_inactive,
        )
    }


@router.post(
    "/warranty-policies",
    response_model=ManagerWarrantyPolicyResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_WARRANTY_POLICY,
)
async def create_manager_warranty_policy(
    payload: ManagerWarrantyPolicyPayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    """
    Create a shared warranty policy with at least one supplier/brand/series/product target.
    Invalid references, incompatible series/brand selection or invalid duration/maintenance
    terms return 400. This defines future coverage selection without rewriting existing
    equipment coverage snapshots. Repeated POSTs have no idempotency receipt.

    Access and scope: system-tenant Manager access is required; these are shared platform
    definitions. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [warranty policy
    contract](https://github.com/mvnby/air-api/blob/main/docs/warranty-policies.md).
    """
    try:
        return await WarrantyService.create_policy(session, payload=payload.model_dump(exclude_unset=True))
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.patch(
    "/warranty-policies/{policy_id}",
    response_model=ManagerWarrantyPolicyResponse,
    operation_id=PATCH_MANAGER_WARRANTY_POLICY,
)
async def patch_manager_warranty_policy(
    policy_id: int,
    payload: ManagerWarrantyPolicyPayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    """
    Update only submitted shared warranty-policy fields. Missing policy returns 404; invalid
    targets, relationships or durations return 400. Omitted series selection is preserved
    and an explicitly empty selection clears it. Existing equipment warranty snapshots are
    not recalculated from the edited definition.

    Access and scope: system-tenant Manager access is required; these are shared platform
    definitions. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [warranty policy
    contract](https://github.com/mvnby/air-api/blob/main/docs/warranty-policies.md).
    """
    try:
        data = await WarrantyService.update_policy(
            session,
            policy_id=policy_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if data is None:
        raise HTTPException(status_code=404, detail="Warranty policy not found")
    return data


@router.get(
    "/equipment/{equipment_id}/warranty-coverages",
    response_model=list[ManagerEquipmentWarrantyCoverageResponse],
    operation_id=LIST_MANAGER_EQUIPMENT_WARRANTY_COVERAGES,
)
async def list_manager_equipment_warranty_coverages(
    equipment_id: int,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read warranty coverage snapshots and their current temporal, maintenance and
    operator-decision status for customer equipment. Missing/inaccessible equipment returns
    404. Reading computes status without changing the stored policy snapshot or recording a
    warranty decision.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [warranty policy
    contract](https://github.com/mvnby/air-api/blob/main/docs/warranty-policies.md).
    """
    coverages = await WarrantyCoverageService.list_coverages(
        session,
        equipment_id=equipment_id,
        tenant_scope=tenant_scope,
    )
    if coverages is None:
        raise HTTPException(status_code=404, detail="Equipment not found")
    return coverages


@router.post(
    "/warranty-coverages/{coverage_id}/decision",
    response_model=ManagerEquipmentWarrantyCoverageResponse,
    operation_id=DECIDE_MANAGER_WARRANTY_COVERAGE,
)
async def decide_manager_warranty_coverage(
    coverage_id: int,
    payload: ManagerWarrantyDecisionPayload,
    username: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Record a voided/restored decision with a required reason for an equipment coverage under
    a coverage lock, appending decision history. Missing/inaccessible equipment/coverage
    returns 404 and invalid action/reason returns 400. Restoring equipment/supplier coverage
    cannot override warranty_mode=none; valid restoration recalculates maintenance status.
    Repeats append decisions because no idempotency receipt is used; shared policy
    definitions remain unchanged.

    Access and scope: Manager access is required; equipment ownership is inherited from its
    customer in the authenticated tenant. Linked orders must also belong to the selected
    storefront. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [warranty policy
    contract](https://github.com/mvnby/air-api/blob/main/docs/warranty-policies.md).
    """
    try:
        data = await WarrantyCoverageService.record_decision(
            session,
            coverage_id=coverage_id,
            action=payload.action,
            reason=payload.reason,
            decided_by=username,
            tenant_scope=tenant_scope,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if data is None:
        raise HTTPException(status_code=404, detail="Warranty coverage not found")
    return data
