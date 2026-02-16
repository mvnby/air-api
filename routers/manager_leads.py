from fastapi import APIRouter

from routers.manager_leads_read import router as manager_leads_read_router
from routers.manager_leads_write import router as manager_leads_write_router


router = APIRouter()
router.include_router(manager_leads_read_router)
router.include_router(manager_leads_write_router)
