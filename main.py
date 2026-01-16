import os
import asyncio
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqladmin import Admin
from starlette.middleware.sessions import SessionMiddleware

from core.database import engine, init_db
from core.config import settings
from core.logger import setup_logging
from routers import admin as admin_router
from routers import api as api_router
from admin import admin_views

# Setup logging with session-specific server.log (cleared on restart)
logger = setup_logging(session_log_file="logs/server.log", clear_session_log=True)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Create tables on startup
    await init_db()
    
    # Start background price sync (every 6 hours)
    from services.scheduler_service import scheduler_service
    asyncio.create_task(scheduler_service.start_loop(interval_hours=settings.SCHEDULER_INTERVAL))
    
    yield

app = FastAPI(lifespan=lifespan)

# --- MIDDLEWARE & ERROR HANDLING ---

@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.exception(f"Unhandled exception: {exc}")
    return JSONResponse(
        status_code=500,
        content={"message": "Internal server error"},
    )

app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(admin_router.router)
app.include_router(api_router.router)

# Static files
app.mount(f"/{settings.STATIC_DIR}", StaticFiles(directory=settings.STATIC_DIR), name="static")

# Setup SQLAdmin
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
admin = Admin(app, engine, title="AirCon Admin", templates_dir=os.path.join(BASE_DIR, "templates"))

# Register views from the admin package
for view in admin_views:
    admin.add_view(view)