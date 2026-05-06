from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.responses import Response

from core.app_constants import MANAGER_ASSETS_DIRNAME, MANAGER_ASSETS_ROUTE
from core.config import settings
from core.logger import logger


MANAGER_NO_CACHE_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}


def apply_manager_no_cache_headers(response: Response) -> Response:
    response.headers.update(MANAGER_NO_CACHE_HEADERS)
    return response


class ManagerAssetsStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope) -> Response:
        response = await super().get_response(path, scope)
        if response.status_code == 200 and path.endswith((".js", ".css")):
            apply_manager_no_cache_headers(response)
        return response


def mount_static_and_media(app: FastAPI, base_dir: Path) -> None:
    static_dir = base_dir / settings.STATIC_DIR
    if not static_dir.exists():
        static_dir.mkdir(parents=True, exist_ok=True)

    app.mount(
        f"/{settings.STATIC_DIR}",
        StaticFiles(directory=static_dir),
        name="static",
    )

    media_dir = base_dir / "media"
    if not media_dir.exists():
        media_dir.mkdir(parents=True, exist_ok=True)
    app.mount("/media", StaticFiles(directory=media_dir), name="media")


def mount_manager_assets(app: FastAPI, manager_dist: Path) -> None:
    logger.info(f"Manager Dist Path: {manager_dist}, Exists: {manager_dist.exists()}")

    if manager_dist.exists():
        app.mount(
            MANAGER_ASSETS_ROUTE,
            ManagerAssetsStaticFiles(directory=manager_dist / MANAGER_ASSETS_DIRNAME),
            name="manager_assets",
        )
    else:
        logger.warning("Manager frontend dist directory not found!")
