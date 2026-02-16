from fastapi import APIRouter

from routers.manager_media_ingest_read import router as manager_media_ingest_read_router
from routers.manager_media_ingest_write import router as manager_media_ingest_write_router


router = APIRouter()
router.include_router(manager_media_ingest_read_router)
router.include_router(manager_media_ingest_write_router)
