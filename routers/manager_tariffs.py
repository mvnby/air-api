from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    LIST_MANAGER_TARIFFS,
    CREATE_MANAGER_TARIFF,
    UPDATE_MANAGER_TARIFF,
    DELETE_MANAGER_TARIFF
)
from schemas import (
    ManagerTariffCreatePayload,
    ManagerTariffUpdatePayload,
    ManagerTariffResponse,
    ManagerTariffListResponse,
    ManagerActionMessageResponse
)
from services.tariffs_service import TariffsService

router = APIRouter(
    prefix="/api/manager/tariffs",
    tags=["manager/tariffs"],
    dependencies=[Depends(get_current_username)]
)

@router.get("", response_model=ManagerTariffListResponse, operation_id=LIST_MANAGER_TARIFFS)
async def list_manager_tariffs(session: AsyncSession = Depends(get_session)):
    items = await TariffsService.get_all_tariffs(session)
    return ManagerTariffListResponse(items=items)

@router.post("", response_model=ManagerTariffResponse, status_code=status.HTTP_201_CREATED, operation_id=CREATE_MANAGER_TARIFF)
async def create_manager_tariff(
    payload: ManagerTariffCreatePayload,
    session: AsyncSession = Depends(get_session)
):
    tariff = await TariffsService.create_tariff(session, payload)
    return tariff

@router.put("/{tariff_id}", response_model=ManagerTariffResponse, operation_id=UPDATE_MANAGER_TARIFF)
async def update_manager_tariff(
    tariff_id: int,
    payload: ManagerTariffUpdatePayload,
    session: AsyncSession = Depends(get_session)
):
    tariff = await TariffsService.update_tariff(session, tariff_id, payload)
    return tariff

@router.delete("/{tariff_id}", response_model=ManagerActionMessageResponse, operation_id=DELETE_MANAGER_TARIFF)
async def delete_manager_tariff(
    tariff_id: int,
    session: AsyncSession = Depends(get_session)
):
    await TariffsService.delete_tariff(session, tariff_id)
    return ManagerActionMessageResponse(message="Tariff deleted successfully")
