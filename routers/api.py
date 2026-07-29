"""Main API router that composes split public/admin route modules."""
from fastapi import APIRouter

from routers.api_admin import router as admin_router
from routers.api_catalog_revision import router as catalog_revision_router
from routers.api_content import router as content_router
from routers.api_product_collections import router as product_collections_router
from routers.api_leads import router as leads_router
from routers.api_orders import router as orders_router
from routers.api_products import router as products_router
from routers.api_proxy import router as proxy_router
from routers.api_yandex_business import router as yandex_business_router

router = APIRouter(prefix="/api", tags=["api"])
router.include_router(admin_router)
router.include_router(catalog_revision_router)
router.include_router(content_router)
router.include_router(leads_router)
router.include_router(orders_router)
router.include_router(products_router)
router.include_router(proxy_router)
router.include_router(product_collections_router)
router.include_router(yandex_business_router)
