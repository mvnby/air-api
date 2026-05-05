from fastapi import FastAPI

from core.app_http import configure_http
from core.app_lifespan import app_lifespan
from core.app_manager import setup_manager_spa
from core.app_observability import init_sentry
from core.app_paths import AppPaths, get_app_paths
from core.app_routing import register_app_routers
from core.app_static import mount_static_and_media


def _configure_app_layers(app: FastAPI, paths: AppPaths) -> None:
    configure_http(app)
    register_app_routers(app)
    mount_static_and_media(app, paths.base_dir)
    setup_manager_spa(app, paths.manager_dist)


def create_app() -> FastAPI:
    init_sentry()

    paths = get_app_paths()
    app = FastAPI(lifespan=app_lifespan)
    _configure_app_layers(app, paths)

    return app
