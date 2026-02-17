import os

from fastapi import FastAPI
from sqladmin import Admin
from sqlalchemy.engine import Engine

from admin import admin_views
from core.security import AdminAuthBackend


def configure_sqladmin(app: FastAPI, engine: Engine, base_dir: str, secret_key: str) -> Admin:
    admin = Admin(
        app,
        engine,
        title="AirCon Admin",
        templates_dir=os.path.join(base_dir, "templates"),
        authentication_backend=AdminAuthBackend(secret_key=secret_key),
    )

    for view in admin_views:
        admin.add_view(view)

    return admin
