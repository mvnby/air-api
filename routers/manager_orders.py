from fastapi import APIRouter

from routers.manager_orders_read import router as manager_orders_read_router
from routers.manager_orders_write import router as manager_orders_write_router


router = APIRouter()
router.include_router(manager_orders_read_router)
router.include_router(manager_orders_write_router)
