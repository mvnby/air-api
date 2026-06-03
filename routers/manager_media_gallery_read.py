from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.security import get_current_username
from routers.manager_operation_ids import (
    GET_COMMON_GALLERY_IMAGES,
    GET_IMAGE_VARIANT_CANDIDATES,
    REUSE_SEARCH,
)
from schemas import (
    CommonGalleryImageResponse,
    ManagerMediaReuseSearchItemResponse,
    ProductImageVariantCandidatesResponse,
)
from services.manager_media_service import ManagerMediaService
from services.product_image_variant_service import ProductImageVariantService


router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.get(
    "/gallery/reuse-search",
    response_model=List[ManagerMediaReuseSearchItemResponse],
    operation_id=REUSE_SEARCH,
)
async def reuse_search(
    q: str = Query(..., min_length=2),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """Search for products to reuse images from."""
    return await ManagerMediaService.search_reuse_products(session, q)


@router.get(
    "/gallery/common-images",
    response_model=List[CommonGalleryImageResponse],
    operation_id=GET_COMMON_GALLERY_IMAGES,
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


@router.get(
    "/gallery/variant-candidates",
    response_model=ProductImageVariantCandidatesResponse,
    operation_id=GET_IMAGE_VARIANT_CANDIDATES,
)
async def get_image_variant_candidates(
    variant_type: str = Query("card", description="Variant to check: original, processed, card, full"),
    limit: int = Query(100, ge=1, le=100),
    include_installation: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """Dry-run candidate selection for images missing a requested variant."""
    try:
        return await ProductImageVariantService.get_missing_variant_candidates(
            session=session,
            variant_type=variant_type,
            limit=limit,
            include_installation=include_installation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
