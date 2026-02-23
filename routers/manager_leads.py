from fastapi import APIRouter

from routers.manager_leads_inbox import router as manager_leads_inbox_router
from routers.manager_leads_read import router as manager_leads_read_router
from routers.manager_leads_write import router as manager_leads_write_router


router = APIRouter()
# Inbox router must come BEFORE write router — the write router has PATCH /{lead_id}
# which would otherwise catch GET /counter and GET /inbox as path-parameter matches.
router.include_router(manager_leads_inbox_router)
router.include_router(manager_leads_read_router)
router.include_router(manager_leads_write_router)
