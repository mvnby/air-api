from fastapi import APIRouter, Request, Depends, HTTPException, UploadFile, File, Form
from typing import Optional, List
from fastapi.responses import RedirectResponse
from services.importer_service import ImporterService
from core.database import async_session_maker
from core.security import get_current_username, check_admin_session
from models import Product, Order
from routers import admin_docs
from sqlmodel import select
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/admin", tags=["admin"])
importer_service = ImporterService()
router.include_router(admin_docs.router)

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

@router.get("/api/admin/installers/search")
async def search_installers(
    q: str = "",
    username: str = Depends(get_current_username)
):
    """
    Search installers for Select2.
    """
    from models import Installer
    async with async_session_maker() as session:
        stmt = select(Installer).where(Installer.is_active == True)
        if q:
            stmt = stmt.where(Installer.name.ilike(f"%{q}%"))
        
        result = await session.execute(stmt)
        installers = result.scalars().all()
        
        return [
            {
                "id": i.id,
                "text": f"{i.name} (TG: {i.telegram_id or '-'})",
                "default_rate": i.default_rate or 0
            }
            for i in installers
        ]

@router.get("/calendar/events")
async def get_calendar_events(
    start: Optional[str] = None,
    end: Optional[str] = None,
    username: str = Depends(get_current_username)
):
    """
    Get events for FullCalendar (Orders with Installation or Assessment dates).
    """
    from models import Order, OrderStatus, OrderInstaller
    from sqlalchemy import or_
    from sqlalchemy.orm import selectinload

    async with async_session_maker() as session:
        # Query orders that have EITHER installation OR assessment date
        # Restrict by date range if provided (FullCalendar sends ISO strings)
        # For simplicity, we fetch all relevant futures for now or simple filter
        
        stmt = select(Order).options(
            selectinload(Order.installers).selectinload(OrderInstaller.installer)
        ).where(
            or_(
                Order.installation_date.is_not(None),
                Order.assessment_date.is_not(None)
            )
        )
        
        if start:
            # Simple optimization: filter roughly if dates are passed
            # In validation phase we can refine strict date filtering
            pass

        result = await session.execute(stmt)
        orders = result.scalars().all()
        
        events = []
        for o in orders:
            # 1. Assessment Event (Blue)
            if o.assessment_date:
                events.append({
                    "id": f"assess_{o.id}",
                    "title": f"🔍 Замер: {o.delivery_address or 'Без адреса'}",
                    "start": o.assessment_date.isoformat(),
                    "color": "#3b82f6", # Blue
                    "extendedProps": {"order_id": o.id}
                })
            
            # 2. Installation Event (Green/Gray)
            if o.installation_date:
                color = "#22c55e" # Green (Confirmed)
                if o.status == OrderStatus.COMPLETED:
                    color = "#6b7280" # Gray (Done)
                elif o.status == OrderStatus.CANCELED:
                    color = "#ef4444" # Red
                
                # Build installer names string
                installers_str = ""
                if o.installers:
                    installers_str = " (" + ", ".join([i.installer.name for i in o.installers if i.installer]) + ")"

                events.append({
                    "id": f"install_{o.id}",
                    "title": f"🛠️ Монтаж: {o.delivery_address or 'Без адреса'}{installers_str}",
                    "start": o.installation_date.isoformat(),
                    "color": color,
                    "extendedProps": {"order_id": o.id}
                })
                
        return events
        
@router.post("/api/upload_images")
async def upload_images(
    files: List[UploadFile],
    slug: Optional[str] = Form(None),
    username: str = Depends(get_current_username)
):
    """
    Bulk upload images for articles/products.
    Returns list of web-accessible URLs.
    """
    from services.image_service import ImageService
    uploaded_urls = []
    
    # Default to 'uploads' if no slug provided (e.g. new article)
    effective_slug = slug or "uploads"
    
    # Determine entity type based on context - defaulting to 'articles' for now 
    # as this is primarily for article editor.
    # Could be made dynamic if needed.
    entity_type = "articles" 
    
    for file in files:
        file_bytes = await file.read()
        filename = file.filename or "image.jpg"
        
        db_path = await ImageService.save_image(
            file_bytes=file_bytes,
            entity_type=entity_type,
            slug=effective_slug,
            filename=filename
        )
        
        web_path = ImageService.get_web_path(db_path)
        uploaded_urls.append(web_path)
        
    return {"urls": uploaded_urls}

@router.get("/api/article_images/{slug}")
async def list_article_images(
    slug: str,
    username: str = Depends(get_current_username)
):
    """
    List all images associated with an article slug.
    """
    from services.image_service import ImageService
    
    # We assume 'articles' entity type
    urls = await ImageService.list_images("articles", slug)
    return {"urls": urls}
