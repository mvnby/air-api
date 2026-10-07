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
    """
    Read feature-library categories in their display order. This shared dictionary has no
    pagination and reading it does not create or assign features.

    Access and scope: Manager access is required; this reads the shared platform catalog,
    not tenant-owned copies. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Read shared feature definitions with category/brand/product/scope filters. Active
    features are shown by default; is_active may select archived definitions. product_id
    checks product existence and returns 404 if missing. total is the returned list length;
    no pagination is accepted.

    Access and scope: Manager access is required; this reads the shared platform catalog,
    not tenant-owned copies. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Create a feature and its automatic rules; is_active defaults to true. New definitions
    support universal or brand ownership; brand features require a valid brand and only
    universal features accept automatic rules. Invalid category, replacement, scope or
    unpublished media returns 400. Returns 201; creation does not assign it to every brand
    product and has no idempotency receipt.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Read candidates where the same active manual feature is assigned without individual
    overrides to every published product in a series. Omitted/empty valid series IDs scans
    all series; returned candidate tokens describe the current source links. This read-only
    report does not create series links or remove product links.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Move only submitted candidate rows from repeated product assignments to series
    assignments, deleting the matching product links in one transaction. Duplicate
    candidates return 400; stale tokens/source links or changed eligibility return 409. Rows
    are locked and revalidated; refresh preview after conflict. This mutates catalog
    inheritance and is not a background job.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Read a shared feature definition, rules and relationships, including archived
    definitions. Missing feature returns 404. Library ownership scope is distinct from
    effective product visibility.

    Access and scope: Manager access is required; this reads the shared platform catalog,
    not tenant-owned copies. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Update supplied definition fields/rules, validating ownership, replacements and media
    readiness. Missing feature returns 404; invalid references, replacement cycles or
    illegal scope changes returns 400. Legacy series/product/derived definitions must be
    migrated to universal or brand before ordinary editing.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Set the feature inactive and return its archived definition; this is not a physical
    delete. Missing feature returns 404. Archiving changes effective catalog projections
    while keeping the stored definition and historical relationships.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Create or update a brand/series feature assignment and overrides; returns 204. Feature
    and target must exist and ownership must allow the target. Invalid scope/media or a
    fourth featured series feature returns 400; missing target returns 404. is_featured
    applies only to series; universal rules resolve separately from stored assignments.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Remove a stored brand/series assignment and return 204. Missing series returns 404; an
    absent brand or assignment is a no-op in the current service. Removal stops that
    inheritance path but does not archive the feature or suppress other rule/product
    assignments.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Read a product feature workspace with explicit assignments, effective
    inherited/rule-derived features and automatic suggestions. Missing product returns 404.
    This is a resolved view of shared catalog features, not only a raw relation list.

    Access and scope: Manager access is required; this reads the shared platform catalog,
    not tenant-owned copies. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Replace a product’s explicit feature assignments, including enabled/hidden overrides,
    then return the resolved workspace. Omitted entries lose their explicit assignment;
    inherited/rule-derived features may remain. Missing product returns 404; duplicate,
    invalid, archived or incompatible features/media returns 400. Writes commit together.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Delete the explicit product assignment and return the resolved workspace. Missing
    product returns 404; missing assignment is a no-op. Inherited or automatic features can
    reappear, so deletion is different from an explicit hidden override.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Revalidate requested suggestion IDs and persist only legacy derived suggestions, then
    return the resolved workspace. Universal automatic rules already resolve without stored
    links. Missing product returns 404; outdated/unavailable suggestions return 409. Refresh
    the workspace before retrying stale suggestions.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
    return await FeatureAssignmentService.apply_product_suggestions(
        session, product_id, payload.feature_ids
    )
