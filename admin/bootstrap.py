from pathlib import Path
from typing import Iterable

from fastapi import FastAPI
from sqladmin import Admin
from sqlalchemy.engine import Engine
from sqladmin.models import ModelView

from admin import admin_views
from core.app_constants import ADMIN_TITLE
from core.security import AdminAuthBackend


def _create_admin(app: FastAPI, engine: Engine, templates_dir: Path, secret_key: str) -> Admin:
    return Admin(
        app,
        engine,
        title=ADMIN_TITLE,
        templates_dir=str(templates_dir),
        authentication_backend=AdminAuthBackend(secret_key=secret_key),
    )


def _register_admin_views(admin: Admin, views: Iterable[type[ModelView]]) -> None:
    for view in views:
        admin.add_view(view)


def configure_sqladmin(app: FastAPI, engine: Engine, base_dir: Path, secret_key: str) -> Admin:
    templates_dir = base_dir / "templates"
    admin = _create_admin(app, engine, templates_dir, secret_key)
    _register_admin_views(admin, admin_views)

    return admin
