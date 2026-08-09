from typing import Literal

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from schemas_features import (
    FeatureCategoryResponse,
    FeatureCreatePayload,
    FeatureTargetLinkPayload,
    FeatureUpdatePayload,
    ManagerFeatureListResponse,
    ManagerFeatureResponse,
    ManagerFeatureSuggestionsApplyPayload,
    ManagerFeatureSeriesMigrationApplyPayload,
    ManagerFeatureSeriesMigrationApplyResponse,
    ManagerFeatureSeriesMigrationPreviewResponse,
    ManagerProductFeaturesUpdatePayload,
    ManagerProductFeatureWorkspaceResponse,
)
from services.feature_assignment_service import FeatureAssignmentService
from services.feature_library_service import FeatureLibraryService
from services.feature_series_migration_service import FeatureSeriesMigrationService
from routers.manager_operation_ids import (
    APPLY_MANAGER_PRODUCT_FEATURE_SUGGESTIONS,
    APPLY_MANAGER_FEATURE_SERIES_MIGRATION,
    ARCHIVE_MANAGER_FEATURE,
    CREATE_MANAGER_FEATURE,
    DELETE_MANAGER_FEATURE_TARGET_LINK,
    DELETE_MANAGER_PRODUCT_FEATURE,
    GET_MANAGER_FEATURE,
    GET_MANAGER_PRODUCT_FEATURES,
    LIST_MANAGER_FEATURE_CATEGORIES,
    LIST_MANAGER_FEATURES,
    PREVIEW_MANAGER_FEATURE_SERIES_MIGRATION,
    UPDATE_MANAGER_FEATURE,
    UPDATE_MANAGER_PRODUCT_FEATURES,
    UPSERT_MANAGER_FEATURE_TARGET_LINK,
)
from routers.manager_permission_policy import ManagerPermissionRoute


router = APIRouter(
    prefix="/api/manager",
    tags=["manager-features"],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/feature-categories",
    response_model=list[FeatureCategoryResponse],
    operation_id=LIST_MANAGER_FEATURE_CATEGORIES,
)
async def list_feature_categories(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await FeatureLibraryService.list_categories(session)


@router.get(
    "/features",
    response_model=ManagerFeatureListResponse,
    operation_id=LIST_MANAGER_FEATURES,
)
async def list_features(
    search: str | None = Query(None),
    category_id: int | None = Query(None),
    brand_id: int | None = Query(None),
    product_id: int | None = Query(None),
    scope_type: Literal["universal", "brand", "series", "product", "derived"] | None = Query(None),
    is_active: bool | None = Query(True),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    items = await FeatureLibraryService.list_features(
        session,
        search=search,
        category_id=category_id,
        brand_id=brand_id,
        product_id=product_id,
        scope_type=scope_type,
        is_active=is_active,
    )
    return ManagerFeatureListResponse(items=items, total=len(items))


@router.post(
    "/features",
    response_model=ManagerFeatureResponse,
    status_code=status.HTTP_201_CREATED,
    operation_id=CREATE_MANAGER_FEATURE,
)
async def create_feature(
    payload: FeatureCreatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await FeatureLibraryService.create_feature(session, payload)


@router.get(
    "/features/series-migration/preview",
    response_model=ManagerFeatureSeriesMigrationPreviewResponse,
    operation_id=PREVIEW_MANAGER_FEATURE_SERIES_MIGRATION,
)
async def preview_feature_series_migration(
    series_ids: list[int] | None = Query(None),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await FeatureSeriesMigrationService.preview(session, series_ids=series_ids)


@router.post(
    "/features/series-migration/apply",
    response_model=ManagerFeatureSeriesMigrationApplyResponse,
    operation_id=APPLY_MANAGER_FEATURE_SERIES_MIGRATION,
)
async def apply_feature_series_migration(
    payload: ManagerFeatureSeriesMigrationApplyPayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await FeatureSeriesMigrationService.apply(session, payload.candidates)


@router.get(
    "/features/{feature_id}",
    response_model=ManagerFeatureResponse,
    operation_id=GET_MANAGER_FEATURE,
)
async def get_feature(
    feature_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await FeatureLibraryService.get_feature(session, feature_id)


@router.patch(
    "/features/{feature_id}",
    response_model=ManagerFeatureResponse,
    operation_id=UPDATE_MANAGER_FEATURE,
)
async def update_feature(
    feature_id: int,
    payload: FeatureUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await FeatureLibraryService.update_feature(session, feature_id, payload)


@router.delete(
    "/features/{feature_id}",
    response_model=ManagerFeatureResponse,
    operation_id=ARCHIVE_MANAGER_FEATURE,
)
async def archive_feature(
    feature_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await FeatureLibraryService.archive_feature(session, feature_id)


@router.put(
    "/features/{feature_id}/{target_type}/{target_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id=UPSERT_MANAGER_FEATURE_TARGET_LINK,
)
async def upsert_target_link(
    feature_id: int,
    target_type: Literal["brand", "series"],
    target_id: int,
    payload: FeatureTargetLinkPayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    await FeatureAssignmentService.upsert_target_link(
        session,
        feature_id=feature_id,
        target_type=target_type,
        target_id=target_id,
        payload=payload,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete(
    "/features/{feature_id}/{target_type}/{target_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    operation_id=DELETE_MANAGER_FEATURE_TARGET_LINK,
)
async def delete_target_link(
    feature_id: int,
    target_type: Literal["brand", "series"],
    target_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    await FeatureAssignmentService.delete_target_link(
        session,
        feature_id=feature_id,
        target_type=target_type,
        target_id=target_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/products/{product_id}/features",
    response_model=ManagerProductFeatureWorkspaceResponse,
    operation_id=GET_MANAGER_PRODUCT_FEATURES,
)
async def get_product_features(
    product_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await FeatureAssignmentService.get_product_workspace(session, product_id)


@router.put(
    "/products/{product_id}/features",
    response_model=ManagerProductFeatureWorkspaceResponse,
    operation_id=UPDATE_MANAGER_PRODUCT_FEATURES,
)
async def update_product_features(
    product_id: int,
    payload: ManagerProductFeaturesUpdatePayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await FeatureAssignmentService.replace_product_assignments(
        session, product_id, payload.assignments
    )


@router.delete(
    "/products/{product_id}/features/{feature_id}",
    response_model=ManagerProductFeatureWorkspaceResponse,
    operation_id=DELETE_MANAGER_PRODUCT_FEATURE,
)
async def delete_product_feature(
    product_id: int,
    feature_id: int,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await FeatureAssignmentService.delete_product_assignment(
        session, product_id, feature_id
    )


@router.post(
    "/products/{product_id}/features/suggestions/apply",
    response_model=ManagerProductFeatureWorkspaceResponse,
    operation_id=APPLY_MANAGER_PRODUCT_FEATURE_SUGGESTIONS,
)
async def apply_product_feature_suggestions(
    product_id: int,
    payload: ManagerFeatureSuggestionsApplyPayload,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    return await FeatureAssignmentService.apply_product_suggestions(
        session, product_id, payload.feature_ids
    )
