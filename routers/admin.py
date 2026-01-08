from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from services.importer_service import ImporterService

router = APIRouter(prefix="/admin", tags=["admin"])
importer_service = ImporterService()

@router.post("/import_onliner")
async def import_process(request: Request):
    form = await request.form()
    url = form.get("url")
    if not url:
        return RedirectResponse(url="/admin/product/list", status_code=303)
        
    try:
        product = await importer_service.import_product(str(url))
        return RedirectResponse(
            url=f"/admin/product/list?msg=Product '{product.title}' imported successfully!&type=success",
            status_code=303
        )
    except Exception as e:
        print(f"Import error: {e}")
        return RedirectResponse(
            url=f"/admin/product/list?msg=Error: {str(e)}&type=danger", 
            status_code=303
        )
