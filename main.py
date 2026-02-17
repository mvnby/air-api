import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from admin.bootstrap import configure_sqladmin
from core.app_static import mount_manager_assets, mount_static_and_media
from core.database import engine, init_db, async_session_maker
from core.app_routing import register_app_routers
from core.config import settings
from core.logger import logger
import sentry_sdk

if settings.SENTRY_DSN:
    sentry_sdk.init(
        dsn=settings.SENTRY_DSN,
        traces_sample_rate=1.0,
        profiles_sample_rate=1.0,
        environment=settings.ENVIRONMENT
    )

from routers.manager_spa import create_manager_spa_router

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Log startup
    logger.info("Starting Application...")
    
    # Create tables on startup
    await init_db()
    
    # Seed data
    from services.installation_service import InstallationService
    async with async_session_maker() as session:
        await InstallationService.seed_defaults(session)
    
    # Start background price sync (every 6 hours)
    from services.scheduler_service import scheduler_service
    asyncio.create_task(scheduler_service.start_loop(interval_hours=settings.SCHEDULER_INTERVAL))
    
    yield
    
    logger.info("Stopping Application...")

app = FastAPI(lifespan=lifespan)

# --- MIDDLEWARE & ERROR HANDLING ---

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception at {request.url}: {exc}")
    
    # If the error happened in Admin Panel, try to return a user-friendly HTML
    if str(request.url.path).startswith("/admin"):
        # We can implement a simple HTML response here or redirect
        return JSONResponse(
            status_code=500,
            content={"error": "Internal Server Error", "detail": str(exc)},
        ) # SQLAdmin usually has its own handler, but this catches unhandled ones
        
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error"},
    )
app.add_middleware(ProxyHeadersMiddleware, trusted_hosts=["*"])
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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
