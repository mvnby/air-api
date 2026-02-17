from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, Form, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.logger import logger
from core.security import get_current_username
from routers.manager_operation_ids import (
    BULK_ADD_GALLERY_IMAGES,
    BULK_DELETE_COMMON_GALLERY_IMAGES,
    BULK_UPLOAD_LOCAL_IMAGES,
    CLEANUP_MEDIA,
    DELETE_IMAGE,
    LINK_SEARCH_RESULT,
    REUSE_IMAGE,
    SET_MAIN_IMAGE,
)
from schemas import BulkGalleryAddRequest, BulkGalleryDeleteRequest
from services.manager_media_orchestrator_service import ManagerMediaOrchestratorService
from services.manager_media_service import ManagerMediaService


router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.post("/gallery/link-search-result", operation_id=LINK_SEARCH_RESULT)
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


@router.post("/gallery/set-main", operation_id=SET_MAIN_IMAGE)
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


@router.delete("/gallery/{image_id}", operation_id=DELETE_IMAGE)
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


@router.post("/gallery/reuse-image", operation_id=REUSE_IMAGE)
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


@router.post("/gallery/bulk-add", operation_id=BULK_ADD_GALLERY_IMAGES)
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


@router.post("/gallery/bulk-upload-local", operation_id=BULK_UPLOAD_LOCAL_IMAGES)
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


@router.post("/gallery/bulk-delete-common", operation_id=BULK_DELETE_COMMON_GALLERY_IMAGES)
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


@router.post("/cleanup-media", operation_id=CLEANUP_MEDIA)
async def cleanup_media(
    dry_run: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """Delete orphaned media files not referenced in DB."""
    logger.info(f"Starting media cleanup (dry_run={dry_run}) by {username}")
    return await ManagerMediaService.cleanup_media(session, dry_run=dry_run)
