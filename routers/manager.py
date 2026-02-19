from fastapi import APIRouter

from routers import manager_auth
from routers import manager_calendar
from routers import manager_catalog
from routers import manager_crm
from routers import manager_docs
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
router.include_router(manager_docs.router)
router.include_router(manager_crm.router)
router.include_router(manager_calendar.router)

