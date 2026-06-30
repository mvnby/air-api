import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from core.config import settings
from core.database import async_session_maker, init_db
from core.logger import logger


async def _seed_installation_defaults() -> None:
    from services.installation_service import InstallationService

    async with async_session_maker() as session:
        await InstallationService.seed_defaults(session)


async def _resume_catalog_import_jobs() -> bool:
    decision = settings.scheduler_control_decision
    if not decision.enabled:
        logger.warning("Catalog import job resume skipped: %s.", decision.reason)
        return False

    from services.catalog_import_runtime_service import catalog_import_runtime_service

    await catalog_import_runtime_service.resume_pending_jobs()
    return True


def _start_scheduler_loop() -> bool:
    decision = settings.scheduler_control_decision
    if not decision.enabled:
        logger.warning("Scheduler startup skipped: %s.", decision.reason)
        return False

    logger.info(
        "Scheduler startup enabled: %s. interval_hours=%s",
        decision.reason,
        settings.SCHEDULER_INTERVAL,
    )
    from services.scheduler_service import scheduler_service

    asyncio.create_task(
        scheduler_service.start_loop(interval_hours=settings.SCHEDULER_INTERVAL)
    )
    return True


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    logger.info("Starting Application...")

    await init_db()
    await _seed_installation_defaults()
    await _resume_catalog_import_jobs()
    _start_scheduler_loop()

    yield

    logger.info("Stopping Application...")
