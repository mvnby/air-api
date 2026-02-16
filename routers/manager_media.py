from fastapi import APIRouter

from routers.manager_media_gallery import router as manager_media_gallery_router
from routers.manager_media_ingest import router as manager_media_ingest_router


router = APIRouter()
router.include_router(manager_media_ingest_router)
router.include_router(manager_media_gallery_router)
