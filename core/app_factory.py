from fastapi import FastAPI
from pathlib import Path

from admin.bootstrap import configure_sqladmin
from core.app_http import configure_http
from core.app_lifespan import app_lifespan
from core.app_manager import setup_manager_spa
from core.app_observability import init_sentry
from core.app_paths import get_base_dir, get_manager_dist
from core.app_routing import register_app_routers
from core.app_static import mount_static_and_media
from core.database import engine
from core.config import settings


def create_app() -> FastAPI:
    init_sentry()

    base_dir: Path = get_base_dir()
    manager_dist: Path = get_manager_dist(base_dir)

    app = FastAPI(lifespan=app_lifespan)

    configure_http(app)
    register_app_routers(app)
    mount_static_and_media(app, base_dir)
    setup_manager_spa(app, manager_dist)

    configure_sqladmin(
        app=app,
        engine=engine,
        base_dir=base_dir,
        secret_key=settings.SECRET_KEY,
    )

    return app
