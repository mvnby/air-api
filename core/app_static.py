import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from core.config import settings
from core.logger import logger


def mount_static_and_media(app: FastAPI, base_dir: str) -> None:
    app.mount(
        f"/{settings.STATIC_DIR}",
        StaticFiles(directory=os.path.join(base_dir, settings.STATIC_DIR)),
        name="static",
    )

    media_dir = os.path.join(base_dir, "media")
    if not os.path.exists(media_dir):
        os.makedirs(media_dir, exist_ok=True)
    app.mount("/media", StaticFiles(directory=media_dir), name="media")


def mount_manager_assets(app: FastAPI, manager_dist: str) -> None:
    logger.info(f"Manager Dist Path: {manager_dist}, Exists: {os.path.exists(manager_dist)}")

    if os.path.exists(manager_dist):
        app.mount(
            "/manager/assets",
            StaticFiles(directory=os.path.join(manager_dist, "assets")),
            name="manager_assets",
        )
    else:
        logger.warning("Manager frontend dist directory not found!")
