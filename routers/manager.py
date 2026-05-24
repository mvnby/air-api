from fastapi import APIRouter

from routers import manager_auth
from routers import manager_backups
from routers import manager_brands
from routers import manager_calendar
from routers import manager_catalog
from routers import manager_crm
from routers import manager_contracts
from routers import manager_dashboard
from routers import manager_docs
from routers import manager_google_auth
from routers import manager_leads
from routers import manager_mail
from routers import manager_media
from routers import manager_orders
from routers import manager_repair_complaints
from routers import manager_specs
from routers import manager_installers
from routers import manager_settings
from routers import manager_service_estimates
from routers import manager_tariffs
from routers import manager_tags
from routers import manager_supply
from routers import manager_yandex_business


router = APIRouter()
router.include_router(manager_backups.router)
router.include_router(manager_google_auth.router)
router.include_router(manager_catalog.router)
router.include_router(manager_media.router)
router.include_router(manager_specs.router)
router.include_router(manager_auth.router)
router.include_router(manager_docs.router)
router.include_router(manager_orders.router)
router.include_router(manager_repair_complaints.router)
router.include_router(manager_leads.router)
router.include_router(manager_mail.router)
router.include_router(manager_crm.router)
router.include_router(manager_contracts.router)
router.include_router(manager_calendar.router)
router.include_router(manager_dashboard.router)
router.include_router(manager_installers.router)
router.include_router(manager_brands.router)
router.include_router(manager_settings.router)
router.include_router(manager_tariffs.router)
router.include_router(manager_service_estimates.router)
router.include_router(manager_tags.router)
router.include_router(manager_supply.router)
router.include_router(manager_yandex_business.router)
