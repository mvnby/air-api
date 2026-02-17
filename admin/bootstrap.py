from pathlib import Path

from fastapi import FastAPI
from sqladmin import Admin
from sqlalchemy.engine import Engine

from admin import admin_views
from core.app_constants import ADMIN_TITLE
from core.security import AdminAuthBackend


def configure_sqladmin(app: FastAPI, engine: Engine, base_dir: Path, secret_key: str) -> Admin:
    templates_dir = base_dir / "templates"

    admin = Admin(
        app,
        engine,
        title=ADMIN_TITLE,
        templates_dir=str(templates_dir),
        authentication_backend=AdminAuthBackend(secret_key=secret_key),
    )

    for view in admin_views:
        admin.add_view(view)

    return admin
