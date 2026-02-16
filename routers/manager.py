from fastapi import APIRouter

from routers import manager_catalog
from routers import manager_leads
from routers import manager_media
from routers import manager_orders
from routers import manager_specs
from routers import manager_tools


router = APIRouter()
router.include_router(manager_catalog.router)
router.include_router(manager_media.router)
router.include_router(manager_specs.router)
router.include_router(manager_tools.router)
router.include_router(manager_orders.router)
router.include_router(manager_leads.router)
