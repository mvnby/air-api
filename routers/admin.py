from fastapi import APIRouter
from routers import admin_analytics
from routers import admin_docs
from routers import admin_import
from routers import admin_media
from routers import admin_orders
from routers import admin_schedule

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(admin_analytics.router)
router.include_router(admin_docs.router)
router.include_router(admin_import.router)
router.include_router(admin_media.router)
router.include_router(admin_orders.router)
router.include_router(admin_schedule.router)
