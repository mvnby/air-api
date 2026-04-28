from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse

from core.app_constants import MANAGER_NOT_BUILT_MESSAGE
from core.app_static import apply_manager_no_cache_headers


def create_manager_spa_router(manager_dist: Path) -> APIRouter:
    router = APIRouter()
    index_path = manager_dist / "index.html"

    def _render_index_or_404():
        if index_path.exists():
            return apply_manager_no_cache_headers(FileResponse(str(index_path)))
        return JSONResponse(status_code=404, content={"message": MANAGER_NOT_BUILT_MESSAGE})

    @router.get("/manager/{full_path:path}", include_in_schema=False)
    async def serve_manager_app(full_path: str):
        return _render_index_or_404()

    @router.get("/manager", include_in_schema=False)
    async def serve_manager_root():
        return _render_index_or_404()

    return router
