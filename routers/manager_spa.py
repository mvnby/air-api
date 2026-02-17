import os

from fastapi import APIRouter
from fastapi.responses import FileResponse, JSONResponse


def create_manager_spa_router(manager_dist: str) -> APIRouter:
    router = APIRouter()

    @router.get("/manager/{full_path:path}")
    async def serve_manager_app(full_path: str):
        index_path = os.path.join(manager_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return JSONResponse(status_code=404, content={"message": "Dashboard not built"})

    @router.get("/manager", include_in_schema=False)
    async def serve_manager_root():
        index_path = os.path.join(manager_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return JSONResponse(status_code=404, content={"message": "Dashboard not built"})

    return router
