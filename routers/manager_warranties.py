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
    coverages = await WarrantyService.list_coverages(
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
    try:
        data = await WarrantyService.record_decision(
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
