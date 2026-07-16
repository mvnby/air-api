from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    CALCULATE_MANAGER_INSTALL_ESTIMATE,
    CREATE_MANAGER_SERVICE_ESTIMATE,
    DELETE_MANAGER_SERVICE_ESTIMATE,
    GET_MANAGER_SERVICE_ESTIMATE,
    GET_MANAGER_SERVICE_ESTIMATE_ORDER_LINES,
    LIST_MANAGER_SERVICE_ESTIMATES,
)
from schemas import (
    ManagerActionMessageResponse,
    ManagerInstallEstimateCalculatePayload,
    ManagerInstallEstimateResponse,
    ManagerInstallEstimateSavePayload,
    ManagerServiceDescriptionMode,
    ManagerServiceEstimateOrderLinesMode,
    ManagerServiceEstimateOrderLinesResponse,
    ManagerServiceEstimateListResponse,
    ManagerServiceEstimateResponse,
)
from services.service_estimate_service import ServiceEstimateService


router = APIRouter(
    prefix="/api/manager/service-estimates",
    tags=["manager/service-estimates"],
    dependencies=[Depends(get_current_username)],
)


@router.post("/calculate", response_model=ManagerInstallEstimateResponse, operation_id=CALCULATE_MANAGER_INSTALL_ESTIMATE)
async def calculate_manager_install_estimate(
    payload: ManagerInstallEstimateCalculatePayload,
    session: AsyncSession = Depends(get_session),
):
    return await ServiceEstimateService.calculate_install_estimate(session, payload)


@router.post(
    "",
    response_model=ManagerServiceEstimateResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_SERVICE_ESTIMATE,
)
async def create_manager_service_estimate(
    payload: ManagerInstallEstimateSavePayload,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    return await ServiceEstimateService.create_install_estimate(
        session=session,
        payload=payload,
        created_by=username,
    )


@router.get("", response_model=ManagerServiceEstimateListResponse, operation_id=LIST_MANAGER_SERVICE_ESTIMATES)
async def list_manager_service_estimates(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    customer_id: int | None = Query(None, ge=1),
    session: AsyncSession = Depends(get_session),
):
    return await ServiceEstimateService.list_estimates(
        session=session,
        page=page,
        limit=limit,
        customer_id=customer_id,
    )


@router.get(
    "/{estimate_id}/order-lines",
    response_model=ManagerServiceEstimateOrderLinesResponse,
    operation_id=GET_MANAGER_SERVICE_ESTIMATE_ORDER_LINES,
)
async def get_manager_service_estimate_order_lines(
    estimate_id: int,
    mode: ManagerServiceEstimateOrderLinesMode = Query(ManagerServiceEstimateOrderLinesMode.detailed),
    description_mode: ManagerServiceDescriptionMode = Query(ManagerServiceDescriptionMode.short),
    session: AsyncSession = Depends(get_session),
):
    return await ServiceEstimateService.get_estimate_order_lines(
        session=session,
        estimate_id=estimate_id,
        mode=mode,
        description_mode=description_mode,
    )


@router.get("/{estimate_id}", response_model=ManagerServiceEstimateResponse, operation_id=GET_MANAGER_SERVICE_ESTIMATE)
async def get_manager_service_estimate(
    estimate_id: int,
    session: AsyncSession = Depends(get_session),
):
    return await ServiceEstimateService.get_estimate_by_id(session=session, estimate_id=estimate_id)


@router.delete(
    "/{estimate_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_SERVICE_ESTIMATE,
)
async def delete_manager_service_estimate(
    estimate_id: int,
    session: AsyncSession = Depends(get_session),
):
    return await ServiceEstimateService.delete_estimate(session=session, estimate_id=estimate_id)
