from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.product_collections import (
    ManagerProductCollectionCreate,
    ManagerProductCollectionItemsPayload,
    ManagerProductCollectionListResponse,
    ManagerProductCollectionPlacementsPayload,
    ManagerProductCollectionResponse,
    ManagerProductCollectionUpdate,
    ProductCollectionPreviewResponse,
)
from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    ARCHIVE_MANAGER_PRODUCT_COLLECTION,
    CREATE_MANAGER_PRODUCT_COLLECTION,
    DUPLICATE_MANAGER_PRODUCT_COLLECTION,
    GET_MANAGER_PRODUCT_COLLECTION,
    LIST_MANAGER_PRODUCT_COLLECTIONS,
    PREVIEW_MANAGER_PRODUCT_COLLECTION,
    REPLACE_MANAGER_PRODUCT_COLLECTION_ITEMS,
    REPLACE_MANAGER_PRODUCT_COLLECTION_PLACEMENTS,
    UPDATE_MANAGER_PRODUCT_COLLECTION,
)
from services.manager_product_collection_service import ManagerProductCollectionService


router = APIRouter(
    prefix="/api/manager/product-collections",
    tags=["manager product collections"],
)


@router.get(
    "",
    response_model=ManagerProductCollectionListResponse,
    operation_id=LIST_MANAGER_PRODUCT_COLLECTIONS,
)
async def list_manager_product_collections(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return {"items": await ManagerProductCollectionService.list_collections(session)}


@router.post(
    "",
    response_model=ManagerProductCollectionResponse,
    operation_id=CREATE_MANAGER_PRODUCT_COLLECTION,
)
async def create_manager_product_collection(
    payload: ManagerProductCollectionCreate,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await ManagerProductCollectionService.create_collection(
        session,
        payload.model_dump(),
    )


@router.get(
    "/{collection_id}",
    response_model=ManagerProductCollectionResponse,
    operation_id=GET_MANAGER_PRODUCT_COLLECTION,
)
async def get_manager_product_collection(
    collection_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await ManagerProductCollectionService.get_collection(session, collection_id)


@router.patch(
    "/{collection_id}",
    response_model=ManagerProductCollectionResponse,
    operation_id=UPDATE_MANAGER_PRODUCT_COLLECTION,
)
async def update_manager_product_collection(
    collection_id: int,
    payload: ManagerProductCollectionUpdate,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await ManagerProductCollectionService.update_collection(
        session,
        collection_id,
        payload.model_dump(exclude_unset=True),
    )


@router.post(
    "/{collection_id}/duplicate",
    response_model=ManagerProductCollectionResponse,
    operation_id=DUPLICATE_MANAGER_PRODUCT_COLLECTION,
)
async def duplicate_manager_product_collection(
    collection_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await ManagerProductCollectionService.duplicate(session, collection_id)


@router.post(
    "/{collection_id}/archive",
    response_model=ManagerProductCollectionResponse,
    operation_id=ARCHIVE_MANAGER_PRODUCT_COLLECTION,
)
async def archive_manager_product_collection(
    collection_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await ManagerProductCollectionService.archive(session, collection_id)


@router.put(
    "/{collection_id}/items",
    response_model=ManagerProductCollectionResponse,
    operation_id=REPLACE_MANAGER_PRODUCT_COLLECTION_ITEMS,
)
async def replace_manager_product_collection_items(
    collection_id: int,
    payload: ManagerProductCollectionItemsPayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await ManagerProductCollectionService.replace_items(
        session,
        collection_id,
        [item.model_dump() for item in payload.items],
    )


@router.put(
    "/{collection_id}/placements",
    response_model=ManagerProductCollectionResponse,
    operation_id=REPLACE_MANAGER_PRODUCT_COLLECTION_PLACEMENTS,
)
async def replace_manager_product_collection_placements(
    collection_id: int,
    payload: ManagerProductCollectionPlacementsPayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await ManagerProductCollectionService.replace_placements(
        session,
        collection_id,
        [placement.model_dump() for placement in payload.placements],
    )


@router.get(
    "/{collection_id}/preview",
    response_model=ProductCollectionPreviewResponse,
    operation_id=PREVIEW_MANAGER_PRODUCT_COLLECTION,
)
async def preview_manager_product_collection(
    collection_id: int,
    surface: str = Query(default="home"),
    slot: str = Query(default="featured_products"),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await ManagerProductCollectionService.preview(
        session,
        collection_id=collection_id,
        surface_key=surface,
        slot_key=slot,
    )
