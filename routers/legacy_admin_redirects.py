from fastapi import APIRouter
from fastapi.responses import RedirectResponse


router = APIRouter(tags=["legacy-admin"], include_in_schema=False)


@router.get("/admin")
@router.get("/admin/")
async def redirect_legacy_admin():
    return RedirectResponse(url="/manager", status_code=307)


@router.get("/admin/{full_path:path}")
async def redirect_legacy_admin_path(full_path: str):
    return RedirectResponse(url="/manager", status_code=307)
