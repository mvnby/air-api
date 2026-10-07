from typing import List

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession

from core.database import get_session
from core.logger import logger
from core.security import get_current_username
from routers.manager_operation_ids import UPLOAD_IMAGE, UPLOAD_LOCAL_IMAGES
from routers.manager_permission_policy import ManagerPermissionRoute
from schemas import ManagerMediaImageLinkResponse, ManagerMediaUploadLocalImagesResponse
from services.manager_media_orchestrator_service import ManagerMediaOrchestratorService


router = APIRouter(
    prefix="/api/manager",
    tags=["manager"],
    route_class=ManagerPermissionRoute,
)


@router.post(
    "/upload-image",
    response_model=ManagerMediaImageLinkResponse,
    operation_id=UPLOAD_IMAGE,
)
async def upload_image(
    url: str = Query(..., description="URL of the image to download"),
    product_id: int = Query(..., description="ID of the product to attach image to"),
    is_installation: bool = Query(False, description="Is this an installation photo?"),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Download a source image, decode/convert it to shared WebP storage and attach it to the
    product. A non-installation upload also sets main_image; installation uploads do not.
    Missing product returns 404; invalid source/image returns 400 and runtime storage
    failure 500. Reusing identical canonical bytes/link does not create another link.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
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


@router.post(
    "/upload-local-images",
    response_model=ManagerMediaUploadLocalImagesResponse,
    operation_id=UPLOAD_LOCAL_IMAGES,
)
async def upload_local_images(
    product_id: int = Query(..., description="ID of the product"),
    files: List[UploadFile] = File(...),
    is_installation: bool = Query(False),
    session: AsyncSession = Depends(get_session),
    username: str = Depends(get_current_username),
):
    """
    Ingest local files into shared WebP product storage and attach successful files in one
    catalog transaction. Invalid individual files may be skipped; uploaded/images report
    accepted results. The first successful non-installation image becomes main only if it
    was missing. Missing product returns 404; repeating identical canonical images can reuse
    existing links.

    Access and scope: system-tenant Manager access is required; this operates on the shared
    platform catalog. See [Manager
    authentication](https://github.com/mvnby/air-api/blob/main/docs/api/authentication.md#manager).
    See [media
    publication](https://github.com/mvnby/air-api/blob/main/docs/catalog-media-publication.md).
    """
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
