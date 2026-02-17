import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.config import settings
from core.database import async_session_maker, init_db
from core.logger import logger


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    logger.info("Starting Application...")

    await init_db()

    from services.installation_service import InstallationService

    async with async_session_maker() as session:
        await InstallationService.seed_defaults(session)

    from services.scheduler_service import scheduler_service

    asyncio.create_task(
        scheduler_service.start_loop(interval_hours=settings.SCHEDULER_INTERVAL)
    )

    yield

    logger.info("Stopping Application...")
