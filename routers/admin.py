from fastapi import APIRouter, Request, Depends
from fastapi.responses import RedirectResponse
from services.importer_service import ImporterService
from core.database import async_session_maker
from core.security import get_current_username, check_admin_session
from routers import admin_docs
from routers import admin_media
from routers import admin_schedule

router = APIRouter(prefix="/admin", tags=["admin"])
importer_service = ImporterService()
router.include_router(admin_docs.router)
router.include_router(admin_media.router)
router.include_router(admin_schedule.router)

@router.get("/stats")
async def get_dashboard_stats(
    request: Request,
    authenticated: bool = Depends(check_admin_session)
):
    """
    Dashboard stats endpoint - uses session-based auth (called from admin panel AJAX).
    """
    from services.analytics_service import AnalyticsService
    async with async_session_maker() as session:
        return await AnalyticsService.get_dashboard_stats(session)

@router.post("/import_onliner")
async def import_process(
    request: Request,
    username: str = Depends(get_current_username)
):
    form = await request.form()
    raw_urls = form.get("url", "")
    with_related = bool(form.get("with_related"))
    
    # Split by newlines, remove \r, and filter empty
    urls = [u.strip().replace('\r', '') for u in str(raw_urls).splitlines() if u.strip()]
    
    if not urls:
        return RedirectResponse(url="/admin/product/list", status_code=303)
        
    try:
        results = await importer_service.import_products_bulk(urls, with_related=with_related)
        success_count = len(results["success"])
        error_count = len(results["errors"])
        
        if success_count == 1 and error_count == 0:
            msg = f"Product imported successfully!"
        else:
            msg = f"Import complete: {success_count} success, {error_count} errors."
            
        if error_count > 0:
            msg += " Check logs for details."
        
        return RedirectResponse(
            url=f"/admin/product/list?msg={msg}&type=success",
            status_code=303
        )
    except Exception as e:
        print(f"Import error: {e}")
        return RedirectResponse(
            url=f"/admin/product/list?msg=Error: {str(e)}&type=danger", 
            status_code=303
        )

@router.post("/update_sync_mode")
async def update_sync_mode(
    request: Request,
    username: str = Depends(get_current_username)
):
    form = await request.form()
    new_mode = form.get("mode")
    if new_mode is not None:
        from services.config_service import ConfigService
        await ConfigService.set_config("sync_mode", str(new_mode))
            
    return RedirectResponse(url="/admin/", status_code=303)

from pydantic import BaseModel

class OrderStatusUpdate(BaseModel):
    order_id: int
    new_status: str

@router.post("/api/order/move")
async def move_order_status(
    data: OrderStatusUpdate,
    username: str = Depends(get_current_username)
):
    """
    API for Kanban drag-and-drop.
    """
    from services.order_service import OrderService
    
    async with async_session_maker() as session:
        # Validate status
        try:
            # Check if status exists in Enum
            from models import OrderStatus
            # Allow case-insensitive match or direct match
            status_enum = None
            for s in OrderStatus:
                if s.value == data.new_status:
                    status_enum = s
                    break
            
            if not status_enum:
                return {"success": False, "error": f"Invalid status: {data.new_status}"}

            success = await OrderService.update_status(session, data.order_id, status_enum)
            return {"success": success}
        except Exception as e:
            return {"success": False, "error": str(e)}
