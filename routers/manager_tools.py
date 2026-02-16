from typing import List, Optional, Set
from datetime import datetime
import asyncio
import json

from fastapi import APIRouter, Depends, HTTPException, Query, status, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlmodel import select
from schemas import (
    BulkSpecUpdate,
    SpecsKeysResponse,
    BulkGalleryAddRequest,
    BulkGalleryDeleteRequest,
    CommonGalleryImageResponse,
    ProductUpdate,
    BulkRoundRequest,
)

from core.database import get_session
from core.config import settings
from core.security import get_current_username
from core.logger import logger
from models import Product, ProductImage, Order, Customer
from services.product_service import ProductService
from services.customer_service import CustomerService
from services.manager_legacy_specs_service import ManagerLegacySpecsService
from services.manager_media_service import ManagerMediaService
from services.manager_specs_service import ManagerSpecsService

router = APIRouter(prefix="/api/manager", tags=["manager"])

@router.get("/me", operation_id="read_user_me")
async def check_auth_status(username: str = Depends(get_current_username)):
    """
    Check if current user is authenticated.
    Returns username if valid, 401 otherwise (via Depends).
    """
    return {"username": username, "status": "authenticated"}

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
    
    # 1. Verify product exists
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Use helper. Default behavior for upload is to set main image if not installation
    # Use helper. Default behavior for upload is to set main image if not installation
    set_main = not is_installation
    return await _process_and_save_image(url, product_id, session, set_main=set_main, is_installation=is_installation)

async def _process_and_save_image(
    url: str, 
    product_id: int, 
    session: AsyncSession, 
    set_main: bool,
    is_installation: bool = False
):
    """Helper to download, convert, save, and link image."""
    try:
        return await ManagerMediaService.process_and_save_image(
            url=url,
            product_id=product_id,
            session=session,
            set_main=set_main,
            is_installation=is_installation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc

async def _save_image_from_bytes(
    image_content: bytes,
    product_id: int,
    session: AsyncSession,
    set_main: bool,
    is_installation: bool = False
):
    """Process bytes, deduplicate file storage by hash, and link to product."""
    try:
        return await ManagerMediaService.save_image_from_bytes(
            image_content=image_content,
            product_id=product_id,
            session=session,
            set_main=set_main,
            is_installation=is_installation,
        )
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
    
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    uploaded_images = []
    
    for file in files:
        try:
            content = await file.read()
            # Set main only if it's the first image and product has no main image? 
            # Or simplified: Local uploads don't auto-set main unless product has NONE.
            
            # Check if product has main image currently
            # (We need to re-fetch or trust the object, but object might be stale if we iterate)
            # Safe bet: separate query or just don't set main for batch uploads to be safe?
            # User request: "possibility to download multiple images". 
            # Let's say: first image in batch becomes main IF product has no main image.
            
            should_set_main = False
            if not product.main_image and not is_installation and len(uploaded_images) == 0:
                 should_set_main = True
                 
            result = await _save_image_from_bytes(content, product_id, session, set_main=should_set_main, is_installation=is_installation)
            uploaded_images.append(result)
            
            # If we set main, update local object to prevent next loop from trying
            if should_set_main:
                product.main_image = result["url"]
                
        except Exception as e:
            logger.error(f"Failed to upload file {file.filename}: {e}")
            # We continue with other files or Validation Error?
            # Let's continue and return what succeeded? Or fail all? 
            # For simplicity, fail on invalid file? Or skip?
            # Let's skip and log.
            pass
            
    return {"uploaded": len(uploaded_images), "images": uploaded_images}

async def _sync_legacy_images(session: AsyncSession, product_id: int):
    """Sync ProductImage records to Product.images JSON field."""
    await ManagerMediaService.sync_legacy_images(session, product_id)

async def _remove_file_if_unreferenced(session: AsyncSession, url: str):
    """Delete physical file only when no ProductImage/Product.main_image references remain."""
    await ManagerMediaService.remove_file_if_unreferenced(session, url)

async def _get_common_gallery_urls(
    session: AsyncSession,
    product_ids: List[int],
    exclude_installation: bool = True,
) -> Set[str]:
    """Get image URLs present in all selected products."""
    return await ManagerMediaService.get_common_gallery_urls(
        session,
        product_ids,
        exclude_installation=exclude_installation,
    )

@router.post("/gallery/link-search-result", operation_id="link_search_result")
async def link_search_result(
    url: str = Query(..., description="URL of the image"),
    product_id: int = Query(..., description="ID of the product"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """Add a search result image to gallery (download and link). Does NOT set as main image."""
    product = await session.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
        
    return await _process_and_save_image(url, product_id, session, set_main=False)

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

    common_urls = await _get_common_gallery_urls(
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
        product_ids = json.loads(product_ids_json)
        if not isinstance(product_ids, list):
            raise ValueError()
        unique_product_ids = list(dict.fromkeys(int(pid) for pid in product_ids))
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid product_ids_json")

    if not unique_product_ids:
        raise HTTPException(status_code=400, detail="product_ids is required")
    if not files:
        raise HTTPException(status_code=400, detail="files is required")

    products_stmt = select(Product.id).where(Product.id.in_(unique_product_ids))
    existing_product_ids = set((await session.execute(products_stmt)).scalars().all())
    missing = sorted(set(unique_product_ids) - existing_product_ids)
    if missing:
        raise HTTPException(status_code=404, detail=f"Products not found: {missing}")

    file_payloads: List[bytes] = []
    for file in files:
        content = await file.read()
        if content:
            file_payloads.append(content)

    try:
        return await ManagerMediaService.bulk_upload_local_images(
            session=session,
            product_ids=unique_product_ids,
            file_payloads=file_payloads,
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

@router.post("/specs/bulk-update", operation_id="bulk_update_specs")
async def bulk_update_specs(
    payload: BulkSpecUpdate,
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """
    Массовое добавление или обновление характеристик.
    Идеально для установки диаметров труб для целой серии кондиционеров сразу.
    """
    logger.info(f"Manager {username} bulk updating specs for {len(payload.product_ids)} products. Op: {payload.operation}")
    
    return await ManagerSpecsService.bulk_update_specs(session, payload)

@router.post("/specs/normalize-legacy", operation_id="normalize_legacy_specs")
async def normalize_legacy_specs(
    dry_run: bool = Query(True, description="Если True - не сохраняет изменения в БД, только показывает пример"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username)
):
    """
    Массовая миграция характеристик.
    Переводит ключи Onliner (кириллица) в System (английский).
    """
    logger.info(f"Starting specs normalization (dry_run={dry_run}) by {username}")
    return await ManagerLegacySpecsService.normalize_legacy_specs(session, dry_run=dry_run)

# =============================================
# Manager List Endpoints (Stitch Integration)
# =============================================

@router.get("/products/list", operation_id="get_manager_products")
async def list_products_for_manager(
    page: int = Query(1, ge=1),
    limit: int = Query(40, ge=1, le=100),
    search: Optional[str] = Query(None),
    is_published: Optional[bool] = Query(None),
    area_min: Optional[int] = Query(None),
    area_max: Optional[int] = Query(None),
    is_inverter: Optional[bool] = Query(None),
    sort: str = Query("newest"),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Paginated product list for manager UI.
    Unlike the public catalog, this can show unpublished products.
    """
    return await ProductService.get_manager_list(
        session, page, limit, search, is_published, area_min, area_max, is_inverter, sort
    )


@router.get("/customers", operation_id="get_manager_customers")
async def list_customers_for_manager(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    search: Optional[str] = Query(None),
    customer_type: Optional[str] = Query(None, alias="type"),
    only_with_orders: bool = Query(True),
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Paginated customer list for manager UI.
    Includes order count per customer.
    """
    return await CustomerService.list_for_manager(
        session=session,
        page=page,
        limit=limit,
        search=search,
        customer_type=customer_type,
        only_with_orders=only_with_orders,
    )


@router.patch("/products/{product_id}", operation_id="update_product")
async def update_product(
    product_id: int,
    data: ProductUpdate,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Update individual product fields.
    """
    update_data = data.dict(exclude_unset=True)
    tag_ids = update_data.pop("tag_ids", None)

    result = await ProductService.update_product(session, product_id, update_data, tag_ids)

    if not result:
        raise HTTPException(status_code=404, detail="Product not found")

    return result


@router.post("/products/bulk-round-price", operation_id="bulk_round_price")
async def bulk_round_price(
    request: BulkRoundRequest,
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Round prices down to the nearest multiple of 50.
    """
    if not request.product_ids:
        return {"message": "No products selected", "updated_count": 0}

    return await ProductService.bulk_round_prices(session, request.product_ids)


@router.get("/tags/all", operation_id="get_all_tags")
async def get_all_tags(
    session: AsyncSession = Depends(get_session),
    _user: str = Depends(get_current_username),
):
    """
    Return all tags grouped by TagGroup for the product editor.
    """
    return await ProductService.get_all_tags(session)
