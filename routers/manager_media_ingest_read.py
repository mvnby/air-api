from typing import List

from fastapi import APIRouter, Depends, Query

from core.logger import logger
from core.security import get_current_username
from routers.manager_operation_ids import SEARCH_IMAGES
from schemas import ManagerMediaImageSearchResultResponse
from services.manager_media_service import ManagerMediaService


router = APIRouter(prefix="/api/manager", tags=["manager"])


@router.post(
    "/search-images",
    response_model=List[ManagerMediaImageSearchResultResponse],
    operation_id=SEARCH_IMAGES,
)
async def search_images(
    q: str = Query(..., description="Query string for image search"),
    max_results: int = 20,
    username: str = Depends(get_current_username),
):
    """
    Search DuckDuckGo remotely for image metadata/URLs using q and max_results. Provider
    failures degrade to an empty successful result. This POST only searches: it does not
    download/store images or change gallery/main-image state. The current max_results
    integer has no explicit route range; there is no pagination or guaranteed stable result
    ordering.

    Access and scope: Manager access is required; this reads the shared platform catalog,
    not tenant-owned copies. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    """
    logger.info(f"Manager {username} searching images for: {q}")
    return await ManagerMediaService.search_images(q, max_results=max_results)
