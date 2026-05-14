from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    CREATE_MANAGER_TARIFF,
    CREATE_MANAGER_TARIFF_RULE,
    DELETE_MANAGER_TARIFF,
    DELETE_MANAGER_TARIFF_RULE,
    LIST_MANAGER_FAVORITE_TARIFF_RULES,
    LIST_MANAGER_QUICK_TARIFFS,
    LIST_MANAGER_TARIFFS,
    LIST_MANAGER_TARIFF_RULES,
    UPDATE_MANAGER_TARIFF,
    UPDATE_MANAGER_TARIFF_RULE,
)
from schemas import (
    ManagerActionMessageResponse,
    ManagerQuickTariffListResponse,
    ManagerTariffCreatePayload,
    ManagerTariffListResponse,
    ManagerTariffResponse,
    ManagerTariffRuleCreatePayload,
    ManagerTariffRuleListResponse,
    ManagerTariffRuleResponse,
    ManagerTariffServiceKind,
    ManagerTariffUpdatePayload,
    ManagerTariffRuleUpdatePayload,
)
from services.tariffs_service import TariffsService

router = APIRouter(
    prefix="/api/manager/tariffs",
    tags=["manager/tariffs"],
    dependencies=[Depends(get_current_username)],
)


@router.get("", response_model=ManagerTariffListResponse, operation_id=LIST_MANAGER_TARIFFS)
async def list_manager_tariffs(
    service_kind: ManagerTariffServiceKind | None = Query(None),
    include_inactive: bool = Query(True),
    session: AsyncSession = Depends(get_session),
):
    items = await TariffsService.get_all_tariffs(
        session=session,
        service_kind=service_kind,
        include_inactive=include_inactive,
    )
    return ManagerTariffListResponse(items=items)


@router.get("/quick-add", response_model=ManagerQuickTariffListResponse, operation_id=LIST_MANAGER_QUICK_TARIFFS)
async def list_manager_quick_tariffs(
    q: str = Query(""),
    service_kind: ManagerTariffServiceKind | None = Query(None),
    limit: int = Query(10, ge=1, le=50),
    session: AsyncSession = Depends(get_session),
):
    items = await TariffsService.list_quick_add_tariffs(
        session=session,
        service_kind=service_kind,
        q=q,
        limit=limit,
    )
    return ManagerQuickTariffListResponse(items=items)


@router.post("", response_model=ManagerTariffResponse, status_code=status.HTTP_201_CREATED, operation_id=CREATE_MANAGER_TARIFF)
async def create_manager_tariff(
    payload: ManagerTariffCreatePayload,
    session: AsyncSession = Depends(get_session),
):
    return await TariffsService.create_tariff(session, payload)


@router.put("/{tariff_id}", response_model=ManagerTariffResponse, operation_id=UPDATE_MANAGER_TARIFF)
async def update_manager_tariff(
    tariff_id: int,
    payload: ManagerTariffUpdatePayload,
    session: AsyncSession = Depends(get_session),
):
    return await TariffsService.update_tariff(session, tariff_id, payload)


@router.delete("/{tariff_id}", response_model=ManagerActionMessageResponse, operation_id=DELETE_MANAGER_TARIFF)
async def delete_manager_tariff(
    tariff_id: int,
    session: AsyncSession = Depends(get_session),
):
    await TariffsService.delete_tariff(session, tariff_id)
    return ManagerActionMessageResponse(message="Tariff deleted successfully")


@router.get(
    "/rules/favorites",
    response_model=ManagerTariffRuleListResponse,
    operation_id=LIST_MANAGER_FAVORITE_TARIFF_RULES,
)
async def list_manager_favorite_tariff_rules(
    service_kind: ManagerTariffServiceKind = Query(...),
    include_inactive: bool = Query(False),
    exclude_tariff_id: int | None = Query(None),
    session: AsyncSession = Depends(get_session),
):
    items = await TariffsService.list_favorite_tariff_rules(
        session=session,
        service_kind=service_kind,
        include_inactive=include_inactive,
        exclude_tariff_id=exclude_tariff_id,
    )
    return ManagerTariffRuleListResponse(items=items)


@router.get(
    "/{tariff_id}/rules",
    response_model=ManagerTariffRuleListResponse,
    operation_id=LIST_MANAGER_TARIFF_RULES,
)
async def list_manager_tariff_rules(
    tariff_id: int,
    include_inactive: bool = Query(True),
    session: AsyncSession = Depends(get_session),
):
    items = await TariffsService.list_tariff_rules(
        session=session,
        tariff_id=tariff_id,
        include_inactive=include_inactive,
    )
    return ManagerTariffRuleListResponse(items=items)


@router.post(
    "/{tariff_id}/rules",
    response_model=ManagerTariffRuleResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_TARIFF_RULE,
)
async def create_manager_tariff_rule(
    tariff_id: int,
    payload: ManagerTariffRuleCreatePayload,
    session: AsyncSession = Depends(get_session),
):
    return await TariffsService.create_tariff_rule(session=session, tariff_id=tariff_id, payload=payload)


@router.put(
    "/{tariff_id}/rules/{rule_id}",
    response_model=ManagerTariffRuleResponse,
    operation_id=UPDATE_MANAGER_TARIFF_RULE,
)
async def update_manager_tariff_rule(
    tariff_id: int,
    rule_id: int,
    payload: ManagerTariffRuleUpdatePayload,
    session: AsyncSession = Depends(get_session),
):
    return await TariffsService.update_tariff_rule(
        session=session,
        tariff_id=tariff_id,
        rule_id=rule_id,
        payload=payload,
    )


@router.delete(
    "/{tariff_id}/rules/{rule_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_TARIFF_RULE,
)
async def delete_manager_tariff_rule(
    tariff_id: int,
    rule_id: int,
    session: AsyncSession = Depends(get_session),
):
    await TariffsService.delete_tariff_rule(session=session, tariff_id=tariff_id, rule_id=rule_id)
    return ManagerActionMessageResponse(message="Tariff rule deleted successfully")
