from typing import List

from fastapi import APIRouter, Depends, Query

from core.logger import logger
from core.security import get_current_username
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
