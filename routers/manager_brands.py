from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    CREATE_MANAGER_BRAND_SERIES,
    CREATE_MANAGER_BRAND,
    DELETE_MANAGER_BRAND_SERIES,
    DELETE_MANAGER_BRAND,
    LIST_MANAGER_BRAND_SERIES,
    LIST_MANAGER_BRANDS,
    UPDATE_MANAGER_BRAND_SERIES,
    UPDATE_MANAGER_BRAND,
)
from schemas import (
    ManagerActionMessageResponse,
    ManagerBrandCreatePayload,
    ManagerBrandListResponse,
    ManagerBrandResponse,
    ManagerBrandSeriesCreatePayload,
    ManagerBrandSeriesListResponse,
    ManagerBrandSeriesResponse,
    ManagerBrandSeriesUpdatePayload,
    ManagerBrandUpdatePayload,
)
from services.manager_brand_service import ManagerBrandService


router = APIRouter(
    prefix="/api/manager/brands",
    tags=["manager brands"],
    dependencies=[Depends(get_current_username)],
)


@router.get("", response_model=ManagerBrandListResponse, operation_id=LIST_MANAGER_BRANDS)
async def list_manager_brands(session: AsyncSession = Depends(get_session)):
    items = await ManagerBrandService.list_brands(session)
    return ManagerBrandListResponse(items=items)


@router.post("", response_model=ManagerBrandResponse, operation_id=CREATE_MANAGER_BRAND)
async def create_manager_brand(
    payload: ManagerBrandCreatePayload,
    session: AsyncSession = Depends(get_session),
):
    created = await ManagerBrandService.create_brand(
        session=session,
        payload=payload.model_dump(exclude_unset=True),
    )
    return ManagerBrandResponse(**created)


@router.put(
    "/{brand_id}",
    response_model=ManagerBrandResponse,
    operation_id=UPDATE_MANAGER_BRAND,
)
async def update_manager_brand(
    brand_id: int,
    payload: ManagerBrandUpdatePayload,
    session: AsyncSession = Depends(get_session),
):
    updated = await ManagerBrandService.update_brand(
        session=session,
        brand_id=brand_id,
        payload=payload.model_dump(exclude_unset=True),
    )
    return ManagerBrandResponse(**updated)


@router.get(
    "/{brand_id}/series",
    response_model=ManagerBrandSeriesListResponse,
    operation_id=LIST_MANAGER_BRAND_SERIES,
)
async def list_manager_brand_series(
    brand_id: int,
    session: AsyncSession = Depends(get_session),
):
    items = await ManagerBrandService.list_brand_series(session=session, brand_id=brand_id)
    return ManagerBrandSeriesListResponse(items=items)


@router.post(
    "/{brand_id}/series",
    response_model=ManagerBrandSeriesResponse,
    operation_id=CREATE_MANAGER_BRAND_SERIES,
)
async def create_manager_brand_series(
    brand_id: int,
    payload: ManagerBrandSeriesCreatePayload,
    session: AsyncSession = Depends(get_session),
):
    created = await ManagerBrandService.create_brand_series(
        session=session,
        brand_id=brand_id,
        payload=payload.model_dump(exclude_unset=True),
    )
    return ManagerBrandSeriesResponse(**created)


@router.put(
    "/{brand_id}/series/{series_id}",
    response_model=ManagerBrandSeriesResponse,
    operation_id=UPDATE_MANAGER_BRAND_SERIES,
)
async def update_manager_brand_series(
    brand_id: int,
    series_id: int,
    payload: ManagerBrandSeriesUpdatePayload,
    session: AsyncSession = Depends(get_session),
):
    updated = await ManagerBrandService.update_brand_series(
        session=session,
        brand_id=brand_id,
        series_id=series_id,
        payload=payload.model_dump(exclude_unset=True),
    )
    return ManagerBrandSeriesResponse(**updated)


@router.delete(
    "/{brand_id}/series/{series_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_BRAND_SERIES,
)
async def delete_manager_brand_series(
    brand_id: int,
    series_id: int,
    session: AsyncSession = Depends(get_session),
):
    await ManagerBrandService.delete_brand_series(
        session=session,
        brand_id=brand_id,
        series_id=series_id,
    )
    return ManagerActionMessageResponse(message="Серия успешно удалена")


@router.delete(
    "/{brand_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_BRAND,
)
async def delete_manager_brand(
    brand_id: int,
    session: AsyncSession = Depends(get_session),
):
    await ManagerBrandService.delete_brand(session=session, brand_id=brand_id)
    return ManagerActionMessageResponse(message="Бренд успешно удален")
