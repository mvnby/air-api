import os
from fastapi import FastAPI

from admin.bootstrap import configure_sqladmin
from core.app_http import configure_http
from core.app_lifespan import app_lifespan
from core.app_observability import init_sentry
from core.app_static import mount_manager_assets, mount_static_and_media
from core.database import engine
from core.app_routing import register_app_routers
from core.config import settings

init_sentry()

from routers.manager_spa import create_manager_spa_router

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = FastAPI(lifespan=app_lifespan)

# --- MIDDLEWARE & ERROR HANDLING ---
configure_http(app)

# Include routers
register_app_routers(app)

# Static files
mount_static_and_media(app, BASE_DIR)

# Manager Dashboard SPA
# 1. Mount assets explicitly to bypass the catch-all
manager_dist = os.path.join(BASE_DIR, "manager_frontend", "dist")

mount_manager_assets(app, manager_dist)

# 2. Catch-all + root routes for manager SPA
app.include_router(create_manager_spa_router(manager_dist))

# Setup SQLAdmin with authentication
configure_sqladmin(app=app, engine=engine, base_dir=BASE_DIR, secret_key=settings.SECRET_KEY)
