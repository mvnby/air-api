from fastapi import FastAPI

from routers import admin as admin_router
from routers import api as api_router
from routers import auth as auth_router
from routers import manager as manager_router
from routers import system as system_router


def register_app_routers(app: FastAPI) -> None:
    app.include_router(admin_router.router)
    app.include_router(auth_router.router)
    app.include_router(api_router.router)
    app.include_router(manager_router.router)
    app.include_router(system_router.router)
