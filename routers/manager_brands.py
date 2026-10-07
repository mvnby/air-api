from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    CREATE_MANAGER_BRAND_SERIES,
    CREATE_MANAGER_BRAND_FEATURE,
    CREATE_MANAGER_BRAND,
    DELETE_MANAGER_BRAND_FEATURE,
    DELETE_MANAGER_BRAND_SERIES,
    DELETE_MANAGER_BRAND,
    LIST_MANAGER_BRAND_FEATURES,
    LIST_MANAGER_BRAND_SERIES,
    LIST_MANAGER_BRANDS,
    UPDATE_MANAGER_BRAND_FEATURE,
    UPDATE_MANAGER_BRAND_SERIES,
    APPLY_MANAGER_SERIES_GALLERY_TO_PRODUCTS,
    UPDATE_MANAGER_BRAND,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    ManagerActionMessageResponse,
    ManagerBrandCreatePayload,
    ManagerBrandFeatureCreatePayload,
    ManagerBrandFeatureListResponse,
    ManagerBrandFeatureResponse,
    ManagerBrandFeatureUpdatePayload,
    ManagerBrandListResponse,
    ManagerBrandResponse,
    ManagerSeriesGalleryApplyPayload,
    ManagerSeriesGalleryApplyResponse,
    ManagerBrandUpdatePayload,
)
from schemas_brand_series import (
    ManagerBrandSeriesCreatePayload,
    ManagerBrandSeriesListResponse,
    ManagerBrandSeriesResponse,
    ManagerBrandSeriesUpdatePayload,
)
from services.manager_brand_service import ManagerBrandService


router = APIRouter(
    prefix="/api/manager/brands",
    tags=["manager brands"],
    dependencies=[Depends(get_current_username)],
    route_class=ManagerPermissionRoute,
)


@router.get("", response_model=ManagerBrandListResponse, operation_id=LIST_MANAGER_BRANDS)
async def list_manager_brands(session: AsyncSession = Depends(get_session)):
    """
    List all brands with product counts, ordered by sort_order and title. No pagination
    parameters are accepted.

    Access and scope: Manager access is required; this reads the shared platform catalog,
    not tenant-owned copies. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    items = await ManagerBrandService.list_brands(session)
    return ManagerBrandListResponse(items=items)


@router.post("", response_model=ManagerBrandResponse, operation_id=CREATE_MANAGER_BRAND)
async def create_manager_brand(
    payload: ManagerBrandCreatePayload,
    session: AsyncSession = Depends(get_session),
):
    """
    Create a shared brand and synchronize its brand tag. Title and generated/requested slug
    must be nonempty; an existing slug or invalid publication media returns 400. This POST
    has no idempotency receipt.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
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
    """
    Update submitted brand fields and synchronize the brand tag when identity changes.
    Missing brand returns 404; conflicting slug, empty title or invalid content media
    returns 400. Semantic no-op edits do not publish a new catalog revision.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    updated = await ManagerBrandService.update_brand(
        session=session,
        brand_id=brand_id,
        payload=payload.model_dump(exclude_unset=True),
    )
    return ManagerBrandResponse(**updated)


@router.get(
    "/{brand_id}/features",
    response_model=ManagerBrandFeatureListResponse,
    operation_id=LIST_MANAGER_BRAND_FEATURES,
)
async def list_manager_brand_features(
    brand_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    List active shared features belonging to one brand with series-assignment counts.
    Missing brand returns 404; this list is not paginated. Creating a brand feature alone
    does not assign it to all brand products.

    Access and scope: Manager access is required; this reads the shared platform catalog,
    not tenant-owned copies. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
    items = await ManagerBrandService.list_brand_features(session=session, brand_id=brand_id)
    return ManagerBrandFeatureListResponse(items=items)


@router.post(
    "/{brand_id}/features",
    response_model=ManagerBrandFeatureResponse,
    operation_id=CREATE_MANAGER_BRAND_FEATURE,
)
async def create_manager_brand_feature(
    brand_id: int,
    payload: ManagerBrandFeatureCreatePayload,
    session: AsyncSession = Depends(get_session),
):
    """
    Create a brand-owned feature through the brand editor. Missing brand returns 404; empty
    title, duplicate slug within the brand or invalid feature media returns 400. Creation
    does not assign the feature to series/products and has no idempotency receipt.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
    created = await ManagerBrandService.create_brand_feature(
        session=session,
        brand_id=brand_id,
        payload=payload.model_dump(exclude_unset=True),
    )
    return ManagerBrandFeatureResponse(**created)


@router.put(
    "/{brand_id}/features/{feature_id}",
    response_model=ManagerBrandFeatureResponse,
    operation_id=UPDATE_MANAGER_BRAND_FEATURE,
)
async def update_manager_brand_feature(
    brand_id: int,
    feature_id: int,
    payload: ManagerBrandFeatureUpdatePayload,
    session: AsyncSession = Depends(get_session),
):
    """
    Update submitted fields of a feature belonging to the requested brand. Missing brand or
    feature returns 404; empty title, duplicate brand slug or invalid media returns 400.
    Assignments to series are preserved.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
    updated = await ManagerBrandService.update_brand_feature(
        session=session,
        brand_id=brand_id,
        feature_id=feature_id,
        payload=payload.model_dump(exclude_unset=True),
    )
    return ManagerBrandFeatureResponse(**updated)


@router.delete(
    "/{brand_id}/features/{feature_id}",
    response_model=ManagerActionMessageResponse,
    operation_id=DELETE_MANAGER_BRAND_FEATURE,
)
async def delete_manager_brand_feature(
    brand_id: int,
    feature_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    Archive an unassigned brand feature by setting it inactive and preserving its
    definition/history. Missing brand or feature returns 404; any series assignment blocks
    archiving with 400. An already archived unassigned feature is a semantic no-op; this is
    not a physical delete.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
    await ManagerBrandService.delete_brand_feature(
        session=session,
        brand_id=brand_id,
        feature_id=feature_id,
    )
    return ManagerActionMessageResponse(message="Фича успешно удалена")


@router.get(
    "/{brand_id}/series",
    response_model=ManagerBrandSeriesListResponse,
    operation_id=LIST_MANAGER_BRAND_SERIES,
)
async def list_manager_brand_series(
    brand_id: int,
    session: AsyncSession = Depends(get_session),
):
    """
    List series belonging to a brand, including hidden series, product counts and feature
    assignments. Missing brand returns 404; no page/limit parameters are accepted.

    Access and scope: Manager access is required; this reads the shared platform catalog,
    not tenant-owned copies. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Create a shared series under the requested brand, validating its feature assignments and
    publication media. Missing brand returns 404; empty title, conflicting slug or invalid
    feature/media choices returns 400. This POST has no idempotency receipt.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
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
    """
    Update submitted series fields and, when supplied, replace feature assignments. Missing
    brand/series returns 404; invalid assignments/media, duplicate slug or including a
    hidden series in the brand showcase returns 400. Feature priority permits at most three
    featured entries.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [feature
    taxonomy](https://github.com/mvnby/air-api/blob/main/docs/catalog/feature-taxonomy-guide.md).
    """
    updated = await ManagerBrandService.update_brand_series(
        session=session,
        brand_id=brand_id,
        series_id=series_id,
        payload=payload.model_dump(exclude_unset=True),
    )
    return ManagerBrandSeriesResponse(**updated)


@router.post(
    "/{brand_id}/series/{series_id}/gallery/apply-to-products",
    response_model=ManagerSeriesGalleryApplyResponse,
    operation_id=APPLY_MANAGER_SERIES_GALLERY_TO_PRODUCTS,
)
async def apply_manager_series_gallery_to_products(
    brand_id: int,
    series_id: int,
    payload: ManagerSeriesGalleryApplyPayload,
    session: AsyncSession = Depends(get_session),
):
    """
    Save the submitted nonempty gallery on the series and add those URLs to every assigned
    product. Existing links are skipped; product main images are not changed. Missing
    brand/series returns 404; empty/invalid media returns 400. Series and product changes
    commit together; this writes state rather than producing a preview.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    result = await ManagerBrandService.apply_series_gallery_to_products(
        session=session,
        brand_id=brand_id,
        series_id=series_id,
        source_urls=payload.source_urls,
    )
    return ManagerSeriesGalleryApplyResponse(**result)


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
    """
    Permanently delete a series and its feature links. Missing brand/series returns 404;
    assigned products block deletion with 400, so hide a used series instead. A repeat after
    deletion returns 404.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
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
    """
    Delete a brand and its unused brand tag. Missing brand returns 404, including after
    prior deletion; products, series or products attached to its tag block deletion with
    400. This is a permanent delete, not hiding a brand.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    await ManagerBrandService.delete_brand(session=session, brand_id=brand_id)
    return ManagerActionMessageResponse(message="Бренд успешно удален")
