from fastapi import APIRouter, Depends, Request
from fastapi.responses import RedirectResponse

from core.security import get_current_username
from services.importer_service import ImporterService


router = APIRouter(tags=["admin-import"])
importer_service = ImporterService()


@router.post("/import_onliner")
async def import_process(
    request: Request,
    username: str = Depends(get_current_username)
):
    form = await request.form()
    raw_urls = form.get("url", "")
    with_related = bool(form.get("with_related"))

    urls = [url.strip().replace("\r", "") for url in str(raw_urls).splitlines() if url.strip()]
    if not urls:
        return RedirectResponse(url="/admin/product/list", status_code=303)

    try:
        results = await importer_service.import_products_bulk(urls, with_related=with_related)
        success_count = len(results["success"])
        error_count = len(results["errors"])

        if success_count == 1 and error_count == 0:
            msg = "Product imported successfully!"
        else:
            msg = f"Import complete: {success_count} success, {error_count} errors."
        if error_count > 0:
            msg += " Check logs for details."

        return RedirectResponse(
            url=f"/admin/product/list?msg={msg}&type=success",
            status_code=303
        )
    except Exception as exc:
        print(f"Import error: {exc}")
        return RedirectResponse(
            url=f"/admin/product/list?msg=Error: {str(exc)}&type=danger",
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
