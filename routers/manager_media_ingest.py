from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.logger import logger
from core.security import get_current_username
from services.manager_media_orchestrator_service import ManagerMediaOrchestratorService
from services.manager_media_service import ManagerMediaService


router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.post("/search-images", response_model=List[dict], operation_id="search_images")
async def search_images(
    q: str = Query(..., description="Query string for image search"),
    max_results: int = 20,
    username: str = Depends(get_current_username),
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
    username: str = Depends(get_current_username),
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
    username: str = Depends(get_current_username),
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
