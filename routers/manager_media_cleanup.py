from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    APPROVE_MAIN_IMAGE_CLEANUP_ITEMS,
    CREATE_MAIN_IMAGE_CLEANUP_BATCH,
    LIST_MAIN_IMAGE_CLEANUP_BATCHES,
    LIST_MAIN_IMAGE_CLEANUP_ITEMS,
    LIST_MAIN_IMAGE_CLEANUP_SKIP_REASONS,
    REJECT_MAIN_IMAGE_CLEANUP_ITEMS,
    SKIP_MAIN_IMAGE_CLEANUP_ITEMS,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    ProductMainImageCleanupApprovePayload,
    ProductMainImageCleanupBatchCreatePayload,
    ProductMainImageCleanupBatchCreateResponse,
    ProductMainImageCleanupBatchListResponse,
    ProductMainImageCleanupDecisionResponse,
    ProductMainImageCleanupItemListResponse,
    ProductMainImageCleanupRejectPayload,
    ProductMainImageCleanupSkipPayload,
    ProductMainImageCleanupSkipReasonsResponse,
)
from services.product_main_image_cleanup_service import ProductMainImageCleanupService


router = APIRouter(
    prefix="/api/manager/main-image-cleanup",
    tags=["manager"],
    route_class=ManagerPermissionRoute,
)


@router.post(
    "/batches",
    response_model=ProductMainImageCleanupBatchCreateResponse,
    operation_id=CREATE_MAIN_IMAGE_CLEANUP_BATCH,
)
async def create_main_image_cleanup_batch(
    payload: ProductMainImageCleanupBatchCreatePayload,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Synchronously create and process a review batch of at most 50 product main-image
    candidates. Existing product/source pairs are skipped; unsupported
    remote/missing/local-transparent sources receive skip reasons. Processing outcomes and
    files are saved, but Product.main_image changes only on approval. Invalid processor
    returns 400. This POST is not a read-only preview or queued worker job.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ProductMainImageCleanupService.create_batch(
            session=session,
            limit=payload.limit,
            processor_method=payload.processor_method,
            created_by=username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/batches",
    response_model=ProductMainImageCleanupBatchListResponse,
    operation_id=LIST_MAIN_IMAGE_CLEANUP_BATCHES,
)
async def list_main_image_cleanup_batches(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Read saved main-image review batches with offset and limit 1–100. Completion of a batch
    means candidate processing ended, not that candidates were approved or product main
    images changed.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await ProductMainImageCleanupService.list_batches(
        session=session,
        limit=limit,
        offset=offset,
    )


@router.get(
    "/items",
    response_model=ProductMainImageCleanupItemListResponse,
    operation_id=LIST_MAIN_IMAGE_CLEANUP_ITEMS,
)
async def list_main_image_cleanup_items(
    batch_id: int | None = Query(None),
    status: str | None = Query(None),
    limit: int = Query(100, ge=1, le=100),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Read saved cleanup candidates/outcomes filtered by batch and/or status, with offset and
    limit 1–100. Unknown batch/status can yield an empty list; this does not process
    candidates or approve their use.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return await ProductMainImageCleanupService.list_items(
        session=session,
        batch_id=batch_id,
        status=status,
        limit=limit,
        offset=offset,
    )


@router.post(
    "/items/approve",
    response_model=ProductMainImageCleanupDecisionResponse,
    operation_id=APPROVE_MAIN_IMAGE_CLEANUP_ITEMS,
)
async def approve_main_image_cleanup_items(
    payload: ProductMainImageCleanupApprovePayload,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Approve ready candidates and immediately set each product main_image to its candidate
    URL, recording approval and catalog invalidation together.
    Missing/not-ready/already-approved items are skipped with reasons; an empty ID selection
    returns 400. No original-image version check is performed, so approval can replace a
    main image edited since candidate creation. Repeat approvals skip approved items.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ProductMainImageCleanupService.approve_items(
            session=session,
            item_ids=payload.item_ids,
            approved_by=username,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/items/reject",
    response_model=ProductMainImageCleanupDecisionResponse,
    operation_id=REJECT_MAIN_IMAGE_CLEANUP_ITEMS,
)
async def reject_main_image_cleanup_items(
    payload: ProductMainImageCleanupRejectPayload,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Mark selected nonapproved cleanup items rejected with an operator reason.
    Missing/already-approved items are skipped; empty ID selection returns 400. This saves
    review state but does not change product fields or delete candidate files; repeating may
    update the review timestamp/reason.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await ProductMainImageCleanupService.reject_items(
            session=session,
            item_ids=payload.item_ids,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/items/skip",
    response_model=ProductMainImageCleanupDecisionResponse,
    operation_id=SKIP_MAIN_IMAGE_CLEANUP_ITEMS,
)
async def skip_main_image_cleanup_items(
    payload: ProductMainImageCleanupSkipPayload,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Mark selected nonapproved cleanup items skipped with an operator-visible reason.
    Missing/already-approved items are reported as skipped; empty ID selection returns 400.
    This changes review state without updating product main images or deleting media.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    try:
        return await ProductMainImageCleanupService.skip_items(
            session=session,
            item_ids=payload.item_ids,
            reason=payload.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get(
    "/skip-reasons",
    response_model=ProductMainImageCleanupSkipReasonsResponse,
    operation_id=LIST_MAIN_IMAGE_CLEANUP_SKIP_REASONS,
)
async def list_main_image_cleanup_skip_reasons(
    username: str = Depends(get_current_username),
):
    """
    Read known machine skip reasons and whether operator-entered reasons are supported. No
    candidate processing or product change occurs.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    return ProductMainImageCleanupService.skip_reasons()
