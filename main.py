import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin
from starlette.middleware.sessions import SessionMiddleware
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from core.database import engine, init_db, async_session_maker
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

from core.security import AdminAuthBackend
from routers import admin as admin_router
from routers import api as api_router
from routers import auth as auth_router
from routers import manager_tools
from admin import admin_views
from starlette.responses import FileResponse

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
app.include_router(admin_router.router)
app.include_router(auth_router.router)
app.include_router(api_router.router)
app.include_router(manager_tools.router)

# Static files
app.mount(f"/{settings.STATIC_DIR}", StaticFiles(directory=os.path.join(BASE_DIR, settings.STATIC_DIR)), name="static")
# Mount media from root 'media' folder (shared volume)
media_dir = os.path.join(BASE_DIR, "media")
if not os.path.exists(media_dir):
    os.makedirs(media_dir, exist_ok=True)
app.mount("/media", StaticFiles(directory=media_dir), name="media")

# Manager Dashboard SPA
# 1. Mount assets explicitly to bypass the catch-all
manager_dist = os.path.join(BASE_DIR, "manager_frontend", "dist")
logger.info(f"Manager Dist Path: {manager_dist}, Exists: {os.path.exists(manager_dist)}")

if os.path.exists(manager_dist):
    app.mount("/manager/assets", StaticFiles(directory=os.path.join(manager_dist, "assets")), name="manager_assets")
else:
    logger.warning("Manager frontend dist directory not found!")

    # 2. Catch-all for SPA routes to serve index.html
@app.get("/manager/{full_path:path}")
async def serve_manager_app(full_path: str):
    index_path = os.path.join(manager_dist, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"message": "Dashboard not built"})
    
# 3. Root redirect/serve for /manager
@app.get("/manager", include_in_schema=False)
async def serve_manager_root():
    index_path = os.path.join(manager_dist, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(status_code=404, content={"message": "Dashboard not built"})

# Setup SQLAdmin with authentication
admin = Admin(
    app, 
    engine, 
    title="AirCon Admin", 
    templates_dir=os.path.join(BASE_DIR, "templates"),
    authentication_backend=AdminAuthBackend(secret_key=settings.SECRET_KEY)
)

# Register views from the admin package
for view in admin_views:
    admin.add_view(view)