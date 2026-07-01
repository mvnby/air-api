import asyncio
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from core.config import settings
from core.database import async_session_maker, init_db
from core.logger import logger
from services.runtime_lock_service import RuntimeLockService


async def _seed_installation_defaults() -> None:
    from services.installation_service import InstallationService

    async with async_session_maker() as session:
        await InstallationService.seed_defaults(session)


async def _bootstrap_database() -> bool:
    decision = settings.db_bootstrap_control_decision
    if not decision.enabled:
        logger.warning("Database bootstrap skipped: %s.", decision.reason)
        return False

    logger.info("Database bootstrap enabled: %s.", decision.reason)
    await init_db()
    await _seed_installation_defaults()
    return True


async def _resume_catalog_import_jobs() -> bool:
    from services.catalog_import_runtime_service import catalog_import_runtime_service

    await catalog_import_runtime_service.resume_pending_jobs()
    return True


async def _acquire_scheduler_runtime_lock():
    decision = settings.scheduler_control_decision
    if not decision.enabled:
        logger.warning("Scheduler runtime startup skipped: %s.", decision.reason)
        return None

    lock = await RuntimeLockService.try_acquire(async_session_maker, "mvn:scheduler")
    if not lock.acquired:
        logger.warning("Scheduler runtime startup skipped: %s.", lock.reason)
        return None

    logger.info("Scheduler runtime lock acquired: %s.", lock.reason)
    return lock


def _start_scheduler_loop(app: FastAPI) -> bool:
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

    app.state.scheduler_task = asyncio.create_task(
        scheduler_service.start_loop(interval_hours=settings.SCHEDULER_INTERVAL)
    )
    return True


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    logger.info("Starting Application...")

    await _bootstrap_database()
    scheduler_lock = await _acquire_scheduler_runtime_lock()
    if scheduler_lock:
        app.state.scheduler_runtime_lock = scheduler_lock
        try:
            await _resume_catalog_import_jobs()
            _start_scheduler_loop(app)
        except Exception:
            await scheduler_lock.release()
            raise

    yield

    scheduler_task = getattr(app.state, "scheduler_task", None)
    if scheduler_task:
        scheduler_task.cancel()
        with suppress(asyncio.CancelledError):
            await scheduler_task
    scheduler_lock = getattr(app.state, "scheduler_runtime_lock", None)
    if scheduler_lock:
        await scheduler_lock.release()

    logger.info("Stopping Application...")
