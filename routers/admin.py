from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from services.importer_service import ImporterService
from core.database import async_session_maker
from models import Product, Order
from sqlmodel import select, func
from sqlalchemy.orm import selectinload

router = APIRouter(prefix="/admin", tags=["admin"])
importer_service = ImporterService()

@router.get("/stats")
async def get_dashboard_stats():
    async with async_session_maker() as session:
        # Total Products
        res = await session.execute(select(func.count(Product.id)))
        total_products = res.scalar() or 0
        
        # Active Products
        res = await session.execute(select(func.count(Product.id)).where(Product.is_published == True))
        active_products = res.scalar() or 0
        
        # Total Orders
        res = await session.execute(select(func.count(Order.id)))
        total_orders = res.scalar() or 0
        
        # Sync Mode
        from models import GlobalConfig
        res = await session.execute(select(GlobalConfig).where(GlobalConfig.key == "sync_mode"))
        sync_config = res.scalar_one_or_none()
        sync_mode = int(sync_config.value) if sync_config else 2
        
        # Latest Imports
        res = await session.execute(select(Product).order_by(Product.created_at.desc()).limit(5))
        latest_items = res.scalars().all()
        
        # Latest Orders
        res = await session.execute(
            select(Order)
            .options(selectinload(Order.customer))
            .order_by(Order.created_at.desc())
            .limit(5)
        )
        latest_orders = res.scalars().all()
        
        return {
            "total_products": total_products,
            "active_products": active_products,
            "total_orders": total_orders,
            "sync_mode": sync_mode,
            "latest_items": [
                {"id": p.id, "title": p.title, "price": p.price, "created_at": p.created_at.strftime("%Y-%m-%d %H:%M")} 
                for p in latest_items
            ],
            "latest_orders": [
                {
                    "id": o.id, 
                    "customer": o.customer.name if o.customer else "N/A", 
                    "phone": o.customer.phone if o.customer else "N/A", 
                    "status": o.status,
                    "created_at": o.created_at.strftime("%Y-%m-%d %H:%M")
                } 
                for o in latest_orders
            ]
        }

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
        from models import GlobalConfig
        async with async_session_maker() as session:
            stmt = select(GlobalConfig).where(GlobalConfig.key == "sync_mode")
            res = await session.execute(stmt)
            config = res.scalar_one_or_none()
            
            if not config:
                config = GlobalConfig(key="sync_mode", value=str(new_mode))
                session.add(config)
            else:
                config.value = str(new_mode)
                config.updated_at = func.now()
            
            await session.commit()
            
    return RedirectResponse(url="/admin/", status_code=303)
