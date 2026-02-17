from pathlib import Path

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse


def create_manager_spa_router(manager_dist: str) -> APIRouter:
    router = APIRouter()
    manager_dist_path = Path(manager_dist)
    index_path = manager_dist_path / "index.html"

    def _render_index_or_404():
        if index_path.exists():
            return FileResponse(str(index_path))
        return JSONResponse(status_code=404, content={"message": "Dashboard not built"})

    @router.get("/manager/{full_path:path}")
    async def serve_manager_app(full_path: str):
        return _render_index_or_404()

    @router.get("/manager", include_in_schema=False)
    async def serve_manager_root():
        return _render_index_or_404()

    return router
