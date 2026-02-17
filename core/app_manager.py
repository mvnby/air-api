from pathlib import Path

from fastapi import FastAPI

from core.app_static import mount_manager_assets
from routers.manager_spa import create_manager_spa_router


def setup_manager_spa(app: FastAPI, manager_dist: Path) -> None:
    mount_manager_assets(app, manager_dist)
    app.include_router(create_manager_spa_router(manager_dist))
