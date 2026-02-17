from fastapi import APIRouter, FastAPI

from routers import admin as admin_router
from routers import api as api_router
from routers import auth as auth_router
from routers import manager as manager_router
from routers import system as system_router

APP_ROUTERS: tuple[APIRouter, ...] = (
    admin_router.router,
    auth_router.router,
    api_router.router,
    manager_router.router,
    system_router.router,
)


def register_app_routers(app: FastAPI) -> None:
    for router in APP_ROUTERS:
        app.include_router(router)
