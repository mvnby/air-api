from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Form, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.logger import logger
from core.security import get_current_username
from routers.manager_operation_ids import (
    APPLY_GALLERY_TO_SERIES,
    BULK_ADD_GALLERY_IMAGES,
    BULK_DELETE_COMMON_GALLERY_IMAGES,
    BULK_UPLOAD_LOCAL_IMAGES,
    CLEANUP_MEDIA,
    CROP_PRODUCT_IMAGE,
    DELETE_IMAGE,
    LINK_SEARCH_RESULT,
    PROCESS_MISSING_IMAGE_VARIANTS,
    REPLACE_PRODUCT_IMAGE_LOCAL,
    REUSE_IMAGE,
    REMOVE_PRODUCT_IMAGE_BACKGROUND,
    REPROCESS_IMAGE_VARIANT,
    SET_MAIN_IMAGE,
)
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import (
    BulkGalleryAddRequest,
    BulkGalleryDeleteRequest,
    ManagerMediaBulkAddResponse,
    ManagerMediaApplySeriesResponse,
    ManagerMediaBulkDeleteResponse,
    ManagerMediaBulkUploadResponse,
    ManagerMediaCleanupResponse,
    ManagerMediaDeleteImageResponse,
    ManagerMediaImageLinkResponse,
    ManagerMediaReuseImageResponse,
    ManagerMediaSetMainImageResponse,
    ProductImageCropPayload,
    ProductImageVariantBatchProcessResponse,
    ProductImageVariantResponse,
)
from services.manager_media_orchestrator_service import ManagerMediaOrchestratorService
from services.manager_media_service import ManagerMediaService
from services.product_image_variant_service import ProductImageVariantService


router = APIRouter(
    prefix="/api/manager",
    tags=["manager"],
    route_class=ManagerPermissionRoute,
)

MAX_LOCAL_CROP_UPLOAD_BYTES = 25 * 1024 * 1024


@router.post(
    "/gallery/link-search-result",
    response_model=ManagerMediaImageLinkResponse,
    operation_id=LINK_SEARCH_RESULT,
)
async def link_search_result(
    url: str = Query(..., description="URL of the image"),
    product_id: int = Query(..., description="ID of the product"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Download/ingest a search-result image into shared managed product storage and attach its
    gallery link. Does not set the main image. Missing product returns 404; invalid
    source/media returns 400 and runtime processing conflict 409. Existing canonical
    product/URL links are reused; this is a catalog write, not search.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ManagerMediaOrchestratorService.link_search_result(
            session=session,
            url=url,
            product_id=product_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/gallery/set-main",
    response_model=ManagerMediaSetMainImageResponse,
    operation_id=SET_MAIN_IMAGE,
)
async def set_main_image(
    image_id: int = Query(..., description="ID of the ProductImage to set as main"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Set Product.main_image to a gallery image’s permitted publication URL. Missing
    image/product and other ValueError validation failures are exposed as 404 by this route.
    Repeating the same selection is a semantic no-op; this does not crop/process the image
    or delete prior media.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ManagerMediaService.set_main_image(session, image_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete(
    "/gallery/{image_id}",
    response_model=ManagerMediaDeleteImageResponse,
    operation_id=DELETE_IMAGE,
)
async def delete_gallery_image(
    image_id: int,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Delete one gallery database link and its variant rows, synchronize legacy product.images
    and clear main_image if it points to that URL. Physical objects are retained for
    deferred garbage collection. Missing link returns 404, including after successful
    deletion.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ManagerMediaService.delete_gallery_image(session, image_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/gallery/{image_id}/crop",
    response_model=ManagerMediaImageLinkResponse,
    operation_id=CROP_PRODUCT_IMAGE,
)
async def crop_product_image(
    image_id: int,
    payload: ProductImageCropPayload,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Crop a gallery source and append a new link or replace the selected link according to
    mode. Replacement rebuilds original-variant metadata and follows an existing main-image
    reference; set_main can select the result for non-installation images. Invalid/missing
    source or crop returns 400. This writes media immediately, preserves installation
    classification and has no idempotency receipt.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ManagerMediaService.crop_gallery_image(
            session=session,
            image_id=image_id,
            x=payload.x,
            y=payload.y,
            width=payload.width,
            height=payload.height,
            mode=payload.mode,
            set_main=payload.set_main,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/gallery/{image_id}/replace-local",
    response_model=ManagerMediaImageLinkResponse,
    operation_id=REPLACE_PRODUCT_IMAGE_LOCAL,
)
async def replace_product_image_local(
    image_id: int,
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Replace one gallery link with browser-prepared image bytes and rebuild its original
    variant without server crop work. Main image follows the replacement when it used the
    old URL; installation classification is kept. Empty file, more than 25 MB, missing
    image/product or invalid media returns 400. Physical old objects remain retained.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        content = await file.read(MAX_LOCAL_CROP_UPLOAD_BYTES + 1)
        if not content:
            raise ValueError("Image file is empty")
        if len(content) > MAX_LOCAL_CROP_UPLOAD_BYTES:
            raise ValueError("Image file exceeds the 25 MB limit")
        return await ManagerMediaService.replace_gallery_image_from_bytes(
            session,
            image_id,
            image_content=content,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/gallery/{image_id}/remove-background",
    response_model=ManagerMediaImageLinkResponse,
    operation_id=REMOVE_PRODUCT_IMAGE_BACKGROUND,
)
async def remove_product_image_background(
    image_id: int,
    provider: str = Query("auto", description="Processing provider: auto, noop, manual, rembg, birefnet, ben"),
    rembg_model: str | None = Query(None, description="Optional rembg model override"),
    mode: str = Query("replace", description="replace current ProductImage URL or append a new image"),
    set_main: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Synchronously process a gallery image with the selected provider/model, replacing its
    link by default; append creates/reuses a separate result link. Unknown mode falls back
    to replace. Existing main-image references follow replacement and set_main is honored
    for non-installation images. Invalid/missing source returns 400; provider/runtime
    conflict returns 409. This is not a processing-job enqueue.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ManagerMediaService.remove_background_gallery_image(
            session=session,
            image_id=image_id,
            provider=provider,
            rembg_model=rembg_model,
            mode=mode,
            set_main=set_main,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/gallery/reuse-image",
    response_model=ManagerMediaReuseImageResponse,
    operation_id=REUSE_IMAGE,
)
async def reuse_image(
    product_id: int = Query(...),
    source_image_url: str = Query(...),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Canonicalize an image source URL, ingesting external sources when necessary, and link it
    to the target product without changing its main image. A fully linked canonical URL is
    reused; original-variant metadata may be repaired. ValueError failures, including
    missing product, are exposed as 404 by this route.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ManagerMediaService.reuse_image_link(session, product_id, source_image_url)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/gallery/bulk-add",
    response_model=ManagerMediaBulkAddResponse,
    operation_id=BULK_ADD_GALLERY_IMAGES,
)
async def bulk_add_gallery_images(
    payload: BulkGalleryAddRequest,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Append canonicalized source URLs to all selected products without removing existing
    gallery links. Existing links are reused; set_main selects the first URL only for
    non-installation images. Missing products return 404; empty/invalid selections or
    sources return 400. Database changes and catalog invalidation commit together; this may
    ingest external sources.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ManagerMediaService.bulk_add_gallery_images(
            session=session,
            product_ids=payload.product_ids,
            source_urls=payload.source_urls,
            is_installation=payload.is_installation,
            skip_existing=payload.skip_existing,
            set_main=payload.set_main,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=exc.args[0]) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/gallery/bulk-upload-local",
    response_model=ManagerMediaBulkUploadResponse,
    operation_id=BULK_UPLOAD_LOCAL_IMAGES,
)
async def bulk_upload_local_images(
    product_ids_json: str = Form(..., description="JSON array of product ids"),
    files: List[UploadFile] = File(...),
    is_installation: bool = Form(False),
    set_main: bool = Form(False),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Upload local files once to shared managed storage and attach their URLs to every
    selected product. product_ids_json must be a nonempty JSON array; missing products
    return 404, invalid/empty selection/files return 400. set_main can select the first
    uploaded URL for non-installation images. Attachments and catalog invalidation commit
    together.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ManagerMediaOrchestratorService.bulk_upload_local_images(
            session=session,
            product_ids_json=product_ids_json,
            files=files,
            is_installation=is_installation,
            set_main=set_main,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post(
    "/gallery/bulk-delete-common",
    response_model=ManagerMediaBulkDeleteResponse,
    operation_id=BULK_DELETE_COMMON_GALLERY_IMAGES,
)
async def bulk_delete_common_gallery_images(
    payload: BulkGalleryDeleteRequest,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Remove selected URLs only when they are common to all selected products under the
    requested installation filter. Invalid/empty selection or URLs outside that intersection
    returns 400. Deletes gallery/variant rows and clears affected main images, but retains
    physical files. A repeat requires recalculating the common intersection.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ManagerMediaService.bulk_delete_common_gallery_images(
            session=session,
            product_ids=payload.product_ids,
            urls=payload.urls,
            exclude_installation=payload.exclude_installation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=exc.args[0]) from exc


@router.post(
    "/gallery/apply-to-series",
    response_model=ManagerMediaApplySeriesResponse,
    operation_id=APPLY_GALLERY_TO_SERIES,
)
async def apply_gallery_to_series(
    product_id: int = Query(..., description="Source product ID"),
    dry_run: bool = Query(False, description="Preview changes without applying them"),
    delete_unreferenced: bool = Query(
        False,
        description="Rejected with 409 because physical media cleanup is deferred",
    ),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Replace sibling products’ non-installation galleries and main images with the source
    product’s gallery/main image, preserving installation photos; source URLs are also
    merged into the series gallery. dry_run=true only reports effects, while the default
    false commits them. Missing source returns 404; absent series/gallery returns 400.
    delete_unreferenced=true always returns 409 because physical deletion is deferred.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ManagerMediaService.apply_gallery_to_series(
            session,
            product_id,
            dry_run=dry_run,
            delete_unreferenced=delete_unreferenced,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post(
    "/gallery/variants/process-missing",
    response_model=ProductImageVariantBatchProcessResponse,
    operation_id=PROCESS_MISSING_IMAGE_VARIANTS,
)
async def process_missing_image_variants(
    variant_type: str = Query("card", description="Variant to process: processed, card, full"),
    limit: int = Query(100, ge=1, le=100),
    include_installation: bool = Query(False),
    dry_run: bool = Query(True),
    provider: str = Query("noop", description="Processing provider: auto, noop, manual, rembg, birefnet, ben"),
    rembg_model: str | None = Query(None, description="Optional rembg model override"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Select up to 100 gallery images lacking a requested variant. dry_run defaults to true
    and only reports candidates; false synchronously processes the bounded batch and saves
    statuses/files with catalog invalidation. Installation photos are excluded by default;
    default provider is noop. Invalid variant/provider returns 400. Inspect per-item
    errors/statuses; an HTTP success can include processing failures.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ProductImageVariantService.process_missing_variants(
            session=session,
            variant_type=variant_type,
            limit=limit,
            include_installation=include_installation,
            dry_run=dry_run,
            provider=provider,
            rembg_model=rembg_model,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/gallery/{image_id}/variants/reprocess",
    response_model=ProductImageVariantResponse,
    operation_id=REPROCESS_IMAGE_VARIANT,
)
async def reprocess_image_variant(
    image_id: int,
    variant_type: str = Query("card", description="Variant to reprocess: processed, card, full"),
    provider: str = Query("noop", description="Processing provider: auto, noop, manual, rembg, birefnet, ben"),
    rembg_model: str | None = Query(None, description="Optional rembg model override"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Synchronously regenerate/retry one gallery image variant and return its saved processing
    state. Missing image returns 404; invalid variant/provider returns 400. Source/provider
    failures may be saved as failed and returned with HTTP success; installation catalog
    variants may be skipped. This is a state change with no job/receipt; inspect
    processing_status/processing_error before retrying.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    try:
        return await ProductImageVariantService.reprocess_variant(
            session=session,
            product_image_id=image_id,
            variant_type=variant_type,
            provider=provider,
            rembg_model=rembg_model,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post(
    "/cleanup-media",
    response_model=ManagerMediaCleanupResponse,
    operation_id=CLEANUP_MEDIA,
)
async def cleanup_media(
    dry_run: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Report orphan candidates under local media/products only when dry_run=true. The default
    dry_run=false returns 409 because physical garbage collection is disabled. deleted_count
    and reclaimed_bytes describe potential deletions; no file is actually removed, and the
    returned file list is capped at 50.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
    logger.info(f"Starting media cleanup (dry_run={dry_run}) by {username}")
    try:
        return await ManagerMediaService.cleanup_media(session, dry_run=dry_run)
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
