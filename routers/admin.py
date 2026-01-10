from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from services.importer_service import ImporterService

router = APIRouter(prefix="/admin", tags=["admin"])
importer_service = ImporterService()

@router.post("/import_onliner")
async def import_process(request: Request):
    form = await request.form()
    raw_urls = form.get("url", "")
    
    # Split by newlines, remove \r, and filter empty
    urls = [u.strip().replace('\r', '') for u in str(raw_urls).splitlines() if u.strip()]
    
    if not urls:
        return RedirectResponse(url="/admin/product/list", status_code=303)
        
    try:
        if len(urls) == 1:
            product = await importer_service.import_product(urls[0])
            msg = f"Product '{product.title}' imported successfully!"
        else:
            results = await importer_service.import_products_bulk(urls)
            success_count = len(results["success"])
            error_count = len(results["errors"])
            msg = f"Bulk import complete: {success_count} success, {error_count} errors."
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
