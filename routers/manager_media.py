from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession

from schemas import (
    BulkGalleryAddRequest,
    BulkGalleryDeleteRequest,
    CommonGalleryImageResponse,
)
from core.database import get_session
from core.security import get_current_username
from core.logger import logger
from services.manager_media_orchestrator_service import ManagerMediaOrchestratorService
from services.manager_media_service import ManagerMediaService


router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.post("/search-images", response_model=List[dict], operation_id="search_images")
async def search_images(
    q: str = Query(..., description="Query string for image search"),
    max_results: int = 20,
    username: str = Depends(get_current_username)
):
    """
    Search for images using DuckDuckGo.
    Returns a list of image objects: {image, width, height, ...}
    """
    logger.info(f"Manager {username} searching images for: {q}")

    return await ManagerMediaService.search_images(q, max_results=max_results)


@router.post("/upload-image", operation_id="upload_image")
async def upload_image(
    url: str = Query(..., description="URL of the image to download"),
    product_id: int = Query(..., description="ID of the product to attach image to"),
    is_installation: bool = Query(False, description="Is this an installation photo?"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """
    Download image from URL, convert to WebP, save to local storage,
    and create a ProductImage record linked to the product.
    """
    logger.info(f"Manager {username} uploading image for product {product_id} from {url}")
    try:
        return await ManagerMediaOrchestratorService.upload_image_from_url(
            session=session,
            url=url,
            product_id=product_id,
            is_installation=is_installation,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.post("/upload-local-images", operation_id="upload_local_images")
async def upload_local_images(
    product_id: int = Query(..., description="ID of the product"),
    files: List[UploadFile] = File(...),
    is_installation: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Upload multiple local files, convert to WebP, and attach to product."""
    logger.info(f"Manager {username} uploading {len(files)} local images for product {product_id}")
    try:
        return await ManagerMediaOrchestratorService.upload_local_images(
            session=session,
            product_id=product_id,
            files=files,
            is_installation=is_installation,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/gallery/link-search-result", operation_id="link_search_result")
async def link_search_result(
    url: str = Query(..., description="URL of the image"),
    product_id: int = Query(..., description="ID of the product"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
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


@router.post("/gallery/set-main", operation_id="set_main_image")
async def set_main_image(
    image_id: int = Query(..., description="ID of the ProductImage to set as main"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Set a specific gallery image as the product's main image."""
    try:
        return await ManagerMediaService.set_main_image(session, image_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/gallery/{image_id}", operation_id="delete_image")
async def delete_gallery_image(
    image_id: int,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Delete an image link; physical file is deleted only if unreferenced globally."""
    try:
        return await ManagerMediaService.delete_gallery_image(session, image_id)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/gallery/reuse-search", operation_id="reuse_search")
async def reuse_search(
    q: str = Query(..., min_length=2),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Search for products to reuse images from."""
    return await ManagerMediaService.search_reuse_products(session, q)


@router.post("/gallery/reuse-image", operation_id="reuse_image")
async def reuse_image(
    product_id: int = Query(...),
    source_image_url: str = Query(...),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Link an existing image URL to another product."""
    try:
        return await ManagerMediaService.reuse_image_link(session, product_id, source_image_url)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get(
    "/gallery/common-images",
    response_model=List[CommonGalleryImageResponse],
    operation_id="get_common_gallery_images",
)
async def get_common_gallery_images(
    product_ids: List[int] = Query(..., description="Selected product IDs"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """Return non-installation images shared by all selected products."""
    if not product_ids:
        raise HTTPException(status_code=400, detail="product_ids is required")

    common_urls = await ManagerMediaService.get_common_gallery_urls(
        session=session,
        product_ids=product_ids,
        exclude_installation=True,
    )
    return [
        CommonGalleryImageResponse(url=url, product_count=len(product_ids))
        for url in sorted(common_urls)
    ]


@router.post("/gallery/bulk-add", operation_id="bulk_add_gallery_images")
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


@router.post("/gallery/bulk-upload-local", operation_id="bulk_upload_local_images")
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


@router.post("/gallery/bulk-delete-common", operation_id="bulk_delete_common_gallery_images")
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


@router.post("/cleanup-media", operation_id="cleanup_media")
async def cleanup_media(
    dry_run: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Delete orphaned media files not referenced in DB."""
    logger.info(f"Starting media cleanup (dry_run={dry_run}) by {username}")
    return await ManagerMediaService.cleanup_media(session, dry_run=dry_run)
