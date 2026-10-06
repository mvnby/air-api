from fastapi import APIRouter, FastAPI
from starlette.routing import Route
from core.config import settings

from routers import api as api_router
from routers import auth as auth_router
from routers import internal_bot as internal_bot_router
from routers import internal_bot_media as internal_bot_media_router
from routers import internal_bot_notifications as internal_bot_notifications_router
from routers import internal_bot_operations as internal_bot_operations_router
from routers import internal_bot_runtime as internal_bot_runtime_router
from routers import internal_bot_voice as internal_bot_voice_router
from routers import legacy_admin_redirects
from routers import manager as manager_router
from routers import system as system_router
from routers import connector_auth
from routers import manager_incoming
from routers import manager_personal_tasks

APP_ROUTERS: tuple[APIRouter, ...] = (
    auth_router.router,
    internal_bot_router.router,
    internal_bot_media_router.router,
    internal_bot_notifications_router.router,
    internal_bot_operations_router.router,
    internal_bot_runtime_router.router,
    internal_bot_voice_router.router,
    api_router.router,
    manager_router.router,
    legacy_admin_redirects.router,
    system_router.router,
    connector_auth.router,
    manager_incoming.router,
    manager_personal_tasks.router,
)


def register_app_routers(app: FastAPI) -> None:
    for router in APP_ROUTERS:
        app.include_router(router)
    if settings.CONNECTOR_ENABLED:
        from services.connector_mcp import ConnectorMCPApplication
        connector = ConnectorMCPApplication()
        app.state.connector_mcp = connector
        app.router.routes.append(Route(
            "/api/connector/mcp", endpoint=connector,
            methods=["GET", "POST", "DELETE"],
        ))
