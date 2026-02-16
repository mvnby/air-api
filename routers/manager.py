from fastapi import APIRouter

from routers import manager_auth
from routers import manager_catalog
from routers import manager_leads
from routers import manager_media
from routers import manager_orders
from routers import manager_specs


router = APIRouter()
router.include_router(manager_catalog.router)
router.include_router(manager_media.router)
router.include_router(manager_specs.router)
router.include_router(manager_auth.router)
router.include_router(manager_orders.router)
router.include_router(manager_leads.router)
