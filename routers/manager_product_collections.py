from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from api_contracts.product_collections import (
    ManagerProductCollectionCreate,
    ManagerProductCollectionItemsPayload,
    ManagerProductCollectionListResponse,
    ManagerProductCollectionPlacementsPayload,
    ManagerProductCollectionProductOptionListResponse,
    ManagerProductCollectionResponse,
    ManagerProductCollectionUpdate,
    ManagerProductCollectionWorkspacePayload,
    ProductCollectionPreviewResponse,
    ProductCollectionRuleOptionsResponse,
)
from core.database import get_session
from core.security import (
    AuthenticatedUser,
    get_current_manager_tenant_scope,
    require_manager_access,
)
from models.tenancy import TenantScope
from routers.manager_operation_ids import (
    ARCHIVE_MANAGER_PRODUCT_COLLECTION,
    CREATE_MANAGER_PRODUCT_COLLECTION,
    DUPLICATE_MANAGER_PRODUCT_COLLECTION,
    GET_MANAGER_PRODUCT_COLLECTION,
    GET_MANAGER_PRODUCT_COLLECTION_RULE_OPTIONS,
    LIST_MANAGER_PRODUCT_COLLECTIONS,
    PREVIEW_MANAGER_PRODUCT_COLLECTION,
    REPLACE_MANAGER_PRODUCT_COLLECTION_ITEMS,
    REPLACE_MANAGER_PRODUCT_COLLECTION_PLACEMENTS,
    SEARCH_MANAGER_PRODUCT_COLLECTION_PRODUCTS,
    UPDATE_MANAGER_PRODUCT_COLLECTION,
    SAVE_MANAGER_PRODUCT_COLLECTION_WORKSPACE,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from services.manager_product_collection_service import ManagerProductCollectionService


router = APIRouter(
    prefix="/api/manager/product-collections",
    tags=["manager product collections"],
    route_class=ManagerPermissionRoute,
)


@router.get(
    "/product-options",
    response_model=ManagerProductCollectionProductOptionListResponse,
    operation_id=SEARCH_MANAGER_PRODUCT_COLLECTION_PRODUCTS,
)
async def search_manager_product_collection_products(
    search: str = Query(min_length=1, max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Search products visible to this storefront for manual collection items. search is
    required and limit is 1–100. Returned commercial data is current scoped projection;
    results are not a certification that each product will pass the chosen placement’s
    eligibility checks.

    Access and scope: Manager access and storefront.collections.manage capability are
    required; collections belong to the authenticated tenant and selected storefront. See
    [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
    return await ManagerProductCollectionService.search_products(
        session,
        tenant_scope=tenant_scope,
        search=search,
        limit=limit,
    )


@router.get(
    "/rule-options",
    response_model=ProductCollectionRuleOptionsResponse,
    operation_id=GET_MANAGER_PRODUCT_COLLECTION_RULE_OPTIONS,
)
async def get_manager_product_collection_rule_options(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read brand, series and resolved-feature filter choices from products visible to the
    selected storefront. This supplies typed rule options, not arbitrary expression
    execution or internal supplier/stock ownership data.

    Access and scope: Manager access and storefront.collections.manage capability are
    required; collections belong to the authenticated tenant and selected storefront. See
    [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
    return await ManagerProductCollectionService.get_rule_options(
        session,
        tenant_scope=tenant_scope,
    )


@router.get(
    "",
    response_model=ManagerProductCollectionListResponse,
    operation_id=LIST_MANAGER_PRODUCT_COLLECTIONS,
)
async def list_manager_product_collections(
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read all collections for the selected storefront with their current metadata and child
    records. No pagination parameters are accepted; draft/published/archived state is
    represented in the response. This does not resolve public slot eligibility or publish a
    collection.

    Access and scope: Manager access and storefront.collections.manage capability are
    required; collections belong to the authenticated tenant and selected storefront. See
    [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
    return {
        "items": await ManagerProductCollectionService.list_collections(
            session,
            tenant_scope=tenant_scope,
        )
    }


@router.post(
    "",
    response_model=ManagerProductCollectionResponse,
    operation_id=CREATE_MANAGER_PRODUCT_COLLECTION,
)
async def create_manager_product_collection(
    payload: ManagerProductCollectionCreate,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Create storefront collection metadata, normalizing its slug and validating
    rules/fallback. Default status is draft, but supplied status is honored. Empty required
    copy or incomplete automatic/hybrid rules returns 400; inaccessible fallback returns
    404; partner internal-stock filters return 403. This does not create items/placements
    and has no idempotency receipt. Concurrent persistence conflicts return 409; reread
    current state before retrying.

    Access and scope: Manager access and storefront.collections.manage capability are
    required; collections belong to the authenticated tenant and selected storefront. See
    [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
    return await ManagerProductCollectionService.create_collection(
        session,
        payload.model_dump(),
        tenant_scope=tenant_scope,
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
    )


@router.get(
    "/{collection_id}",
    response_model=ManagerProductCollectionResponse,
    operation_id=GET_MANAGER_PRODUCT_COLLECTION,
)
async def get_manager_product_collection(
    collection_id: int,
    session: AsyncSession = Depends(get_session),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Read a saved storefront collection and its items/placements. Missing or out-of-scope
    collection returns 404. Product commercial data is resolved separately at preview/public
    read time; this response describes editorial configuration.

    Access and scope: Manager access and storefront.collections.manage capability are
    required; collections belong to the authenticated tenant and selected storefront. See
    [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
    return await ManagerProductCollectionService.get_collection(
        session,
        collection_id,
        tenant_scope=tenant_scope,
    )


@router.patch(
    "/{collection_id}",
    response_model=ManagerProductCollectionResponse,
    operation_id=UPDATE_MANAGER_PRODUCT_COLLECTION,
)
async def update_manager_product_collection(
    collection_id: int,
    payload: ManagerProductCollectionUpdate,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Update only submitted collection metadata/rules within the selected storefront.
    Missing/out-of-scope collection or fallback returns 404; invalid combined
    fields/self-fallback/rules returns 400; partner internal-stock rules return 403.
    Items/placements are edited separately or with workspace. No expected_version is
    accepted. Concurrent persistence conflicts return 409; reread current state before
    retrying.

    Access and scope: Manager access and storefront.collections.manage capability are
    required; collections belong to the authenticated tenant and selected storefront. See
    [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
    return await ManagerProductCollectionService.update_collection(
        session,
        collection_id,
        payload.model_dump(exclude_unset=True),
        tenant_scope=tenant_scope,
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
    )


@router.post(
    "/{collection_id}/duplicate",
    response_model=ManagerProductCollectionResponse,
    operation_id=DUPLICATE_MANAGER_PRODUCT_COLLECTION,
)
async def duplicate_manager_product_collection(
    collection_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Create a separate draft copy of collection metadata/rules and still-visible manual
    items. Placements are not copied, so the copy does not claim the source slots;
    hidden/unavailable source items are omitted. Missing/out-of-scope source returns 404.
    Each successful POST creates a new collection and has no idempotency receipt. Concurrent
    persistence conflicts return 409; reread current state before retrying.

    Access and scope: Manager access and storefront.collections.manage capability are
    required; collections belong to the authenticated tenant and selected storefront. See
    [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
    return await ManagerProductCollectionService.duplicate(
        session,
        collection_id,
        tenant_scope=tenant_scope,
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
    )


@router.post(
    "/{collection_id}/archive",
    response_model=ManagerProductCollectionResponse,
    operation_id=ARCHIVE_MANAGER_PRODUCT_COLLECTION,
)
async def archive_manager_product_collection(
    collection_id: int,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Set collection status to archived and record audit/invalidation, retaining its
    items/placements. Missing/out-of-scope collection returns 404. This removes it from
    public active resolution rather than physically deleting it; repeats can create another
    audit update. Concurrent persistence conflicts return 409; reread current state before
    retrying.

    Access and scope: Manager access and storefront.collections.manage capability are
    required; collections belong to the authenticated tenant and selected storefront. See
    [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
    return await ManagerProductCollectionService.archive(
        session,
        collection_id,
        tenant_scope=tenant_scope,
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
    )


@router.put(
    "/{collection_id}/items",
    response_model=ManagerProductCollectionResponse,
    operation_id=REPLACE_MANAGER_PRODUCT_COLLECTION_ITEMS,
)
async def replace_manager_product_collection_items(
    collection_id: int,
    payload: ManagerProductCollectionItemsPayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Replace the entire ordered manual item list, retaining pin/editorial-note settings and
    removing omitted entries. Missing/out-of-scope collection or unavailable products
    returns 404; duplicate product IDs return 400. Parent collection is locked and
    items/audit/invalidation commit together. Visibility checks do not guarantee placement
    eligibility; no expected_version is accepted. Concurrent persistence conflicts return
    409; reread current state before retrying.

    Access and scope: Manager access and storefront.collections.manage capability are
    required; collections belong to the authenticated tenant and selected storefront. See
    [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
    return await ManagerProductCollectionService.replace_items(
        session,
        collection_id,
        [item.model_dump() for item in payload.items],
        tenant_scope=tenant_scope,
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
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
    auth: AuthenticatedUser = Depends(require_manager_access),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Replace all placements for a collection, deleting omitted assignments and saving
    per-slot display/schedule settings. Missing/out-of-scope collection returns 404;
    duplicate surface/slot pairs or invalid keys returns 400. Parent collection is locked;
    audit and invalidation commit with the replacement. Publishing still depends on
    collection status, schedule and resolver eligibility. Concurrent persistence conflicts
    return 409; reread current state before retrying.

    Access and scope: Manager access and storefront.collections.manage capability are
    required; collections belong to the authenticated tenant and selected storefront. See
    [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
    return await ManagerProductCollectionService.replace_placements(
        session,
        collection_id,
        [placement.model_dump() for placement in payload.placements],
        tenant_scope=tenant_scope,
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
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
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Resolve a saved collection for a requested surface/slot using current visible product
    data, rule eligibility, minimum count, fallback and placement layout. Drafts can be
    previewed without publishing. Daily rotation uses the UTC date; independent preview does
    not guarantee this collection wins the public slot. Missing/out-of-scope collection
    returns 404; no writes or draft edits are saved.

    Access and scope: Manager access and storefront.collections.manage capability are
    required; collections belong to the authenticated tenant and selected storefront. See
    [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
    return await ManagerProductCollectionService.preview(
        session,
        collection_id=collection_id,
        surface_key=surface,
        slot_key=slot,
        tenant_scope=tenant_scope,
    )


@router.put(
    "/{collection_id}/workspace",
    response_model=ManagerProductCollectionResponse,
    operation_id=SAVE_MANAGER_PRODUCT_COLLECTION_WORKSPACE,
)
async def save_manager_product_collection_workspace(
    collection_id: int,
    payload: ManagerProductCollectionWorkspacePayload,
    session: AsyncSession = Depends(get_session),
    auth: AuthenticatedUser = Depends(require_manager_access),
    tenant_scope: TenantScope = Depends(get_current_manager_tenant_scope),
):
    """
    Atomically update collection fields and replace its full item/placement sets, with audit
    and invalidation in one transaction. Parent lock serializes metadata and child edits;
    any failure rolls everything back. Unknown/out-of-scope references return 404, invalid
    duplicates/rules/fields 400, partner internal-stock rules 403. No expected_version is
    accepted; this saves directly rather than creating an unpublished revision. Concurrent
    persistence conflicts return 409; reread current state before retrying.

    Access and scope: Manager access and storefront.collections.manage capability are
    required; collections belong to the authenticated tenant and selected storefront. See
    [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [collection
    contract](https://github.com/mvnby/air-api/blob/main/docs/product-collections.md).
    """
    return await ManagerProductCollectionService.save_workspace(
        session,
        collection_id,
        payload.collection.model_dump(exclude_unset=True),
        items=[item.model_dump() for item in payload.items],
        placements=[placement.model_dump() for placement in payload.placements],
        tenant_scope=tenant_scope,
        actor_username=auth.username,
        actor_staff_user_id=auth.staff_user_id,
    )
