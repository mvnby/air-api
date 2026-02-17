from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from core.config import settings
from core.logger import logger


def mount_static_and_media(app: FastAPI, base_dir: Path) -> None:
    app.mount(
        f"/{settings.STATIC_DIR}",
        StaticFiles(directory=base_dir / settings.STATIC_DIR),
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
            "/manager/assets",
            StaticFiles(directory=manager_dist / "assets"),
            name="manager_assets",
        )
    else:
        logger.warning("Manager frontend dist directory not found!")
