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
    REUSE_IMAGE,
    REMOVE_PRODUCT_IMAGE_BACKGROUND,
    REPROCESS_IMAGE_VARIANT,
    SET_MAIN_IMAGE,
)
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


router = APIRouter(prefix="/api/manager", tags=["manager"])


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
    """Add a search result image to gallery (download and link). Does NOT set as main image."""
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
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
    """Set a specific gallery image as the product's main image."""
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
    """Delete an image link; physical file is deleted only if unreferenced globally."""
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
    """Crop a concrete ProductImage and either append or replace the gallery image."""
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
    """Remove background from a ProductImage and replace it by default."""
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
        raise HTTPException(status_code=500, detail=str(exc)) from exc


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
    """Link an existing image URL to another product."""
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
    """Append image links to selected products without removing existing gallery items."""
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
    """Upload local files once and attach to all selected products."""
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
    """Delete selected common image links from selected products only."""
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
    delete_unreferenced: bool = Query(False, description="Delete physical files that become unreferenced"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """Replace sibling products' non-installation galleries with this product's gallery."""
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
    """Dry-run or explicitly process a bounded batch of missing image variants."""
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
    """Retry/reprocess a failed or skipped image variant."""
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
    """Delete orphaned media files not referenced in DB."""
    logger.info(f"Starting media cleanup (dry_run={dry_run}) by {username}")
    return await ManagerMediaService.cleanup_media(session, dry_run=dry_run)
