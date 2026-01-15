from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from services.document_service import DocumentService
from services.importer_service import ImporterService
from core.database import async_session_maker
from models import Product, Order
from sqlmodel import select, func
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/admin", tags=["admin"])
importer_service = ImporterService()

@router.get("/stats")
async def get_dashboard_stats():
    from services.analytics_service import AnalyticsService
    async with async_session_maker() as session:
        return await AnalyticsService.get_dashboard_stats(session)

@router.post("/import_onliner")
async def import_process(request: Request):
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
async def update_sync_mode(request: Request):
    form = await request.form()
    new_mode = form.get("mode")
    if new_mode is not None:
        from services.config_service import ConfigService
        await ConfigService.set_config("sync_mode", str(new_mode))
            
    return RedirectResponse(url="/admin/", status_code=303)

@router.get("/docs/google/{order_id}")
async def open_google_contract(order_id: int):
    """
    Генерирует (или открывает) договор в Google Docs.
    """
    from core.database import async_session_maker # Локальный импорт если нужно
    
    async with async_session_maker() as session:
        link = await DocumentService.create_google_contract(session, order_id)
    
    # Если вернулась ссылка (начинается на http), делаем редирект
    if link.startswith("http"):
        return RedirectResponse(url=link)
    else:
        # Если вернулась ошибка текстом
        return {"error": link}