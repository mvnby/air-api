from typing import Optional

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.manager_api_errors import manager_http_error
from core.manager_error_codes import BAD_REQUEST, CUSTOMER_NOT_FOUND, EQUIPMENT_NOT_FOUND
from core.security import get_current_username
from routers.manager_operation_ids import (
    CREATE_MANAGER_EQUIPMENT_COMPONENT,
    CREATE_MANAGER_EQUIPMENT,
    CREATE_MANAGER_EQUIPMENT_FROM_ORDER,
    CREATE_MANAGER_EQUIPMENT_HISTORY,
    CREATE_MANAGER_EQUIPMENT_HISTORY_FROM_REPAIR_ORDER,
    GET_MANAGER_EQUIPMENT,
    LIST_MANAGER_EQUIPMENT,
    LIST_MANAGER_EQUIPMENT_HISTORY,
    PATCH_MANAGER_EQUIPMENT_COMPONENT,
    PATCH_MANAGER_EQUIPMENT,
)
from schemas import (
    ManagerEquipmentComponentCreatePayload,
    ManagerEquipmentComponentItemResponse,
    ManagerEquipmentComponentUpdatePayload,
    ManagerEquipmentCreatePayload,
    ManagerEquipmentDetailResponse,
    ManagerEquipmentFromOrderPayload,
    ManagerEquipmentFromOrderResponse,
    ManagerEquipmentHistoryFromRepairOrderPayload,
    ManagerEquipmentItemResponse,
    ManagerEquipmentListResponse,
    ManagerEquipmentServiceHistoryCreatePayload,
    ManagerEquipmentServiceHistoryItemResponse,
    ManagerEquipmentServiceHistoryListResponse,
    ManagerEquipmentUpdatePayload,
)
from services.equipment_service import EquipmentService


router = APIRouter(prefix="/api/manager/equipment", tags=["manager-equipment"])


@router.get("", response_model=ManagerEquipmentListResponse, operation_id=LIST_MANAGER_EQUIPMENT)
async def list_manager_equipment(
    customer_id: Optional[int] = Query(None),
    customer_branch_id: Optional[int] = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    include_archived: bool = Query(False),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await EquipmentService.list_equipment(
            session=session,
            customer_id=customer_id,
            customer_branch_id=customer_branch_id,
            page=page,
            limit=limit,
            include_archived=include_archived,
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=LIST_MANAGER_EQUIPMENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=LIST_MANAGER_EQUIPMENT,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.post(
    "",
    response_model=ManagerEquipmentItemResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_EQUIPMENT,
)
async def create_manager_equipment(
    payload: ManagerEquipmentCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await EquipmentService.create_equipment(
            session=session,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_EQUIPMENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_EQUIPMENT,
            error_code=CUSTOMER_NOT_FOUND,
        )
    return data


@router.post(
    "/from-order/{order_id}",
    response_model=ManagerEquipmentFromOrderResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_EQUIPMENT_FROM_ORDER,
)
async def create_manager_equipment_from_order(
    order_id: int,
    payload: ManagerEquipmentFromOrderPayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        return await EquipmentService.create_equipment_from_order(
            session=session,
            order_id=order_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_EQUIPMENT_FROM_ORDER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc


@router.get("/{equipment_id}", response_model=ManagerEquipmentDetailResponse, operation_id=GET_MANAGER_EQUIPMENT)
async def get_manager_equipment(
    equipment_id: int,
    history_limit: int = Query(10, ge=0, le=100),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    data = await EquipmentService.get_equipment_detail(
        session=session,
        equipment_id=equipment_id,
        history_limit=history_limit,
    )
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=GET_MANAGER_EQUIPMENT,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.patch("/{equipment_id}", response_model=ManagerEquipmentItemResponse, operation_id=PATCH_MANAGER_EQUIPMENT)
async def patch_manager_equipment(
    equipment_id: int,
    payload: ManagerEquipmentUpdatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await EquipmentService.update_equipment(
            session=session,
            equipment_id=equipment_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_EQUIPMENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_EQUIPMENT,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.post(
    "/{equipment_id}/components",
    response_model=ManagerEquipmentComponentItemResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_EQUIPMENT_COMPONENT,
)
async def create_manager_equipment_component(
    equipment_id: int,
    payload: ManagerEquipmentComponentCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await EquipmentService.create_component(
            session=session,
            equipment_id=equipment_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_EQUIPMENT_COMPONENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_EQUIPMENT_COMPONENT,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.patch(
    "/{equipment_id}/components/{component_id}",
    response_model=ManagerEquipmentComponentItemResponse,
    operation_id=PATCH_MANAGER_EQUIPMENT_COMPONENT,
)
async def patch_manager_equipment_component(
    equipment_id: int,
    component_id: int,
    payload: ManagerEquipmentComponentUpdatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await EquipmentService.update_component(
            session=session,
            equipment_id=equipment_id,
            component_id=component_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=PATCH_MANAGER_EQUIPMENT_COMPONENT,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=PATCH_MANAGER_EQUIPMENT_COMPONENT,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.get(
    "/{equipment_id}/history",
    response_model=ManagerEquipmentServiceHistoryListResponse,
    operation_id=LIST_MANAGER_EQUIPMENT_HISTORY,
)
async def list_manager_equipment_history(
    equipment_id: int,
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    data = await EquipmentService.list_history(
        session=session,
        equipment_id=equipment_id,
        page=page,
        limit=limit,
    )
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=LIST_MANAGER_EQUIPMENT_HISTORY,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.post(
    "/{equipment_id}/history",
    response_model=ManagerEquipmentServiceHistoryItemResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_EQUIPMENT_HISTORY,
)
async def create_manager_equipment_history(
    equipment_id: int,
    payload: ManagerEquipmentServiceHistoryCreatePayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await EquipmentService.add_history(
            session=session,
            equipment_id=equipment_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_EQUIPMENT_HISTORY,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_EQUIPMENT_HISTORY,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data


@router.post(
    "/{equipment_id}/history/from-repair-order",
    response_model=ManagerEquipmentServiceHistoryItemResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_EQUIPMENT_HISTORY_FROM_REPAIR_ORDER,
)
async def create_manager_equipment_history_from_repair_order(
    equipment_id: int,
    payload: ManagerEquipmentHistoryFromRepairOrderPayload,
    _: str = Depends(get_current_username),
    session: AsyncSession = Depends(get_session),
):
    try:
        data = await EquipmentService.add_history_from_repair_order(
            session=session,
            equipment_id=equipment_id,
            payload=payload.model_dump(exclude_unset=True),
        )
    except ValueError as exc:
        raise manager_http_error(
            status_code=400,
            endpoint=CREATE_MANAGER_EQUIPMENT_HISTORY_FROM_REPAIR_ORDER,
            error_code=BAD_REQUEST,
            message=str(exc),
        ) from exc
    if data is None:
        raise manager_http_error(
            status_code=404,
            endpoint=CREATE_MANAGER_EQUIPMENT_HISTORY_FROM_REPAIR_ORDER,
            error_code=EQUIPMENT_NOT_FOUND,
        )
    return data
