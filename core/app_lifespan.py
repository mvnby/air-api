import asyncio
import os
import signal
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI

from core.config import settings
from core.database import async_session_maker, init_db
from core.logger import logger
from services.runtime_lock_service import RuntimeLockService


_SCHEDULER_RUNTIME_STATUSES = {
    "disabled",
    "waiting_lock",
    "fencing",
    "running",
    "retrying",
    "faulted",
    "stopped",
}
_SCHEDULER_RUNTIME_REASONS = {
    "runtime_control_disabled",
    "lock_acquisition_pending",
    "previous_owner_fencing",
    "scheduler_loop_running",
    "attempt_failed_retry_scheduled",
    "ownership_lost",
    "scheduler_loop_failed",
    "application_shutdown",
}
_SCHEDULER_MIN_FENCING_GRACE_SECONDS = 12


class SchedulerRuntimeFatal(RuntimeError):
    """A post-start failure that requires terminating the whole process."""


class SchedulerOwnershipLost(SchedulerRuntimeFatal):
    """The scheduler can no longer prove exclusive runtime ownership."""


_detached_scheduler_probe_tasks: set[asyncio.Task] = set()


async def _verify_private_attachment_storage() -> None:
    from services.private_attachment_storage_service import (
        verify_private_attachment_storage_startup,
    )

    await verify_private_attachment_storage_startup(settings)


def _verify_google_vision_credentials() -> None:
    from services.google_vision_runtime import (
        verify_google_vision_credentials_startup,
    )

    verify_google_vision_credentials_startup(settings)


def _discard_detached_scheduler_probe(task: asyncio.Task) -> None:
    _detached_scheduler_probe_tasks.discard(task)
    try:
        task.result()
    except asyncio.CancelledError:
        pass
    except Exception:
        logger.exception("Detached scheduler lock probe failed during cleanup.")


def _detach_scheduler_probe(task: asyncio.Task) -> None:
    _detached_scheduler_probe_tasks.add(task)
    task.add_done_callback(_discard_detached_scheduler_probe)


def _scheduler_runtime_fail_stop() -> None:
    """Kill the container so threads and subprocesses cannot outlive ownership."""
    logger.critical(
        "Scheduler runtime entered a fatal state; terminating the process for fencing."
    )
    os.kill(os.getpid(), signal.SIGKILL)


def _set_scheduler_runtime_snapshot(
    app: FastAPI,
    *,
    expected: bool,
    status: str,
    reason: str,
) -> None:
    if status not in _SCHEDULER_RUNTIME_STATUSES:
        raise ValueError(f"unsupported scheduler runtime status: {status}")
    if reason not in _SCHEDULER_RUNTIME_REASONS:
        raise ValueError(f"unsupported scheduler runtime reason: {reason}")
    app.state.scheduler_runtime = {
        "expected": expected,
        "status": status,
        "reason": reason,
        "changed_at": datetime.now(timezone.utc).isoformat(),
    }


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

    return await catalog_import_runtime_service.resume_pending_jobs()


async def _resume_catalog_import_jobs_once(app: FastAPI) -> bool:
    if getattr(app.state, "catalog_import_jobs_resumed", False):
        return False

    resumed = await _resume_catalog_import_jobs()
    if resumed:
        app.state.catalog_import_jobs_resumed = True
    return resumed


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


def _scheduler_runtime_retry_seconds() -> int:
    return max(1, int(settings.RUNTIME_LOCK_RETRY_SECONDS or 15))


def _scheduler_lock_check_seconds() -> int:
    return min(_scheduler_runtime_retry_seconds(), 5)


def _scheduler_lock_probe_timeout_seconds() -> int:
    return min(_scheduler_lock_check_seconds(), 3)


def _scheduler_lock_fencing_grace_seconds() -> int:
    return max(
        _SCHEDULER_MIN_FENCING_GRACE_SECONDS,
        _scheduler_lock_check_seconds()
        + _scheduler_lock_probe_timeout_seconds()
        + 1,
    )


async def _wait_before_scheduler_retry() -> None:
    retry_seconds = _scheduler_runtime_retry_seconds()
    logger.warning("Scheduler runtime will retry in %ss.", retry_seconds)
    await asyncio.sleep(retry_seconds)


async def _wait_for_scheduler_lock_fencing(runtime_lock) -> None:
    grace_seconds = _scheduler_lock_fencing_grace_seconds()
    logger.info(
        "Scheduler runtime lock fencing started: grace_seconds=%s.",
        grace_seconds,
    )
    await asyncio.sleep(grace_seconds)
    await _probe_scheduler_runtime_lock(
        runtime_lock,
        timeout_message="scheduler runtime lock fencing probe timed out",
        lost_message="scheduler runtime lock was lost during fencing",
    )


async def _probe_scheduler_runtime_lock(
    runtime_lock,
    *,
    timeout_message: str,
    lost_message: str,
) -> None:
    """Probe ownership without waiting for a stuck driver's cancellation cleanup."""
    probe_task = asyncio.create_task(runtime_lock.is_held())
    try:
        done, _pending = await asyncio.wait(
            {probe_task},
            timeout=_scheduler_lock_probe_timeout_seconds(),
        )
    except asyncio.CancelledError:
        probe_task.cancel()
        _detach_scheduler_probe(probe_task)
        raise

    if not done:
        probe_task.cancel()
        _detach_scheduler_probe(probe_task)
        raise SchedulerOwnershipLost(timeout_message)

    try:
        lock_is_held = probe_task.result()
    except asyncio.CancelledError as exc:
        raise SchedulerOwnershipLost(timeout_message) from exc
    except Exception as exc:
        raise SchedulerOwnershipLost(lost_message) from exc
    if not lock_is_held:
        raise SchedulerOwnershipLost(lost_message)


async def _monitor_scheduler_runtime_lock(scheduler_task, runtime_lock) -> None:
    check_interval = _scheduler_lock_check_seconds()
    while True:
        try:
            await asyncio.wait_for(
                asyncio.shield(scheduler_task),
                timeout=check_interval,
            )
        except asyncio.CancelledError as exc:
            current_task = asyncio.current_task()
            if current_task is not None and current_task.cancelling():
                raise
            raise SchedulerRuntimeFatal(
                "scheduler loop was cancelled unexpectedly"
            ) from exc
        except asyncio.TimeoutError:
            await _probe_scheduler_runtime_lock(
                runtime_lock,
                timeout_message="scheduler runtime lock probe timed out",
                lost_message="scheduler runtime lock was lost",
            )
        except Exception as exc:
            raise SchedulerRuntimeFatal(
                "scheduler loop failed unexpectedly"
            ) from exc
        else:
            raise SchedulerRuntimeFatal("scheduler loop stopped unexpectedly")


async def _cancel_scheduler_task(scheduler_task) -> None:
    scheduler_task.cancel()
    try:
        await scheduler_task
    except asyncio.CancelledError:
        current_task = asyncio.current_task()
        if current_task is not None and current_task.cancelling():
            raise
    except Exception:
        # The attempt error is logged by the supervisor. Cleanup still owns the
        # runtime lock and must continue to release it before retrying.
        pass


async def _run_scheduler_attempt(app: FastAPI) -> None:
    runtime_lock = None
    scheduler_task = None
    scheduler_work_started = False
    try:
        _set_scheduler_runtime_snapshot(
            app,
            expected=True,
            status="waiting_lock",
            reason="lock_acquisition_pending",
        )
        runtime_lock = await RuntimeLockService.wait_until_acquired(
            async_session_maker,
            "mvn:scheduler",
            required=True,
        )
        if not runtime_lock.acquired:
            logger.error("Scheduler runtime lock unavailable: %s.", runtime_lock.reason)
            return

        app.state.scheduler_runtime_lock = runtime_lock
        logger.info("Scheduler runtime lock acquired: %s.", runtime_lock.reason)
        _set_scheduler_runtime_snapshot(
            app,
            expected=True,
            status="fencing",
            reason="previous_owner_fencing",
        )
        await _wait_for_scheduler_lock_fencing(runtime_lock)
        await _resume_catalog_import_jobs_once(app)
        if not _start_scheduler_loop(app):
            raise RuntimeError("scheduler loop did not start")

        scheduler_task = app.state.scheduler_task
        # create_task() cannot run the child until this coroutine yields, so
        # recording ownership here happens before any scheduler work executes.
        scheduler_work_started = True
        app.state.scheduler_work_started = True
        await asyncio.sleep(0)
        if scheduler_task.done():
            if scheduler_task.cancelled():
                raise SchedulerRuntimeFatal(
                    "scheduler loop was cancelled during startup"
                )
            scheduler_error = scheduler_task.exception()
            if scheduler_error is not None:
                raise SchedulerRuntimeFatal(
                    "scheduler loop failed during startup"
                ) from scheduler_error
            raise SchedulerRuntimeFatal("scheduler loop stopped during startup")
        _set_scheduler_runtime_snapshot(
            app,
            expected=True,
            status="running",
            reason="scheduler_loop_running",
        )
        await _monitor_scheduler_runtime_lock(scheduler_task, runtime_lock)
    except SchedulerRuntimeFatal as exc:
        reason = (
            "ownership_lost"
            if isinstance(exc, SchedulerOwnershipLost)
            else "scheduler_loop_failed"
        )
        _set_scheduler_runtime_snapshot(
            app,
            expected=True,
            status="faulted",
            reason=reason,
        )
        logger.critical("Scheduler runtime fail-stop: %s", exc)
        if scheduler_task is not None and not scheduler_task.done():
            scheduler_task.cancel()
        app.state.scheduler_fail_stop_initiated = True
        try:
            _scheduler_runtime_fail_stop()
        except BaseException:
            logger.exception("Scheduler runtime fail-stop callback returned an error.")
        # Production never reaches this await. It prevents an injected test
        # callback (or a broken fail-stop implementation) from reacquiring.
        await asyncio.Future()
    finally:
        try:
            if scheduler_task is not None:
                try:
                    await _cancel_scheduler_task(scheduler_task)
                finally:
                    if getattr(app.state, "scheduler_task", None) is scheduler_task:
                        app.state.scheduler_task = None
        finally:
            if runtime_lock is not None:
                try:
                    if runtime_lock.acquired:
                        await runtime_lock.release()
                except asyncio.CancelledError:
                    raise
                except Exception:
                    logger.exception(
                        "Scheduler runtime lock cleanup failed; retrying safely."
                    )
                finally:
                    if getattr(app.state, "scheduler_runtime_lock", None) is runtime_lock:
                        app.state.scheduler_runtime_lock = None
                    if scheduler_work_started:
                        app.state.scheduler_work_started = False


async def _run_scheduler_supervisor(app: FastAPI) -> None:
    while True:
        try:
            await _run_scheduler_attempt(app)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduler runtime attempt failed.")

        _set_scheduler_runtime_snapshot(
            app,
            expected=True,
            status="retrying",
            reason="attempt_failed_retry_scheduled",
        )
        await _wait_before_scheduler_retry()


def _start_scheduler_supervisor(app: FastAPI) -> bool:
    existing_task = getattr(app.state, "scheduler_supervisor_task", None)
    if existing_task is not None and not existing_task.done():
        logger.warning("Scheduler runtime supervisor is already running.")
        return False

    decision = settings.scheduler_control_decision
    if not decision.enabled:
        app.state.scheduler_work_started = False
        app.state.scheduler_fail_stop_initiated = False
        _set_scheduler_runtime_snapshot(
            app,
            expected=False,
            status="disabled",
            reason="runtime_control_disabled",
        )
        logger.warning("Scheduler runtime startup skipped: %s.", decision.reason)
        return False

    app.state.scheduler_work_started = False
    app.state.scheduler_fail_stop_initiated = False
    logger.info("Scheduler runtime supervisor started: %s.", decision.reason)
    _set_scheduler_runtime_snapshot(
        app,
        expected=True,
        status="waiting_lock",
        reason="lock_acquisition_pending",
    )
    app.state.scheduler_supervisor_task = asyncio.create_task(
        _run_scheduler_supervisor(app),
        name="scheduler-runtime-supervisor",
    )
    return True


async def _stop_scheduler_supervisor(app: FastAPI) -> None:
    supervisor_task = getattr(app.state, "scheduler_supervisor_task", None)
    if supervisor_task is None:
        return

    runtime_lock = getattr(app.state, "scheduler_runtime_lock", None)
    scheduler_work_started = bool(
        getattr(app.state, "scheduler_work_started", False)
    )
    scheduler_ownership_active = bool(
        scheduler_work_started
        and runtime_lock is not None
        and runtime_lock.acquired
        and not getattr(app.state, "scheduler_fail_stop_initiated", False)
    )
    if scheduler_ownership_active:
        logger.critical(
            "Scheduler loop is active during application shutdown; "
            "terminating the process before releasing runtime ownership."
        )
        app.state.scheduler_fail_stop_initiated = True
        try:
            _scheduler_runtime_fail_stop()
        except BaseException:
            logger.exception(
                "Scheduler shutdown fail-stop callback returned an error."
            )
        # SIGKILL never returns in production. Keeping this fallback makes the
        # shutdown sequence testable with an injected callback while preserving
        # the critical ordering: fail-stop first, then cancellation and unlock.
        logger.critical(
            "Scheduler shutdown fail-stop callback returned; "
            "continuing controlled cleanup fallback."
        )

    try:
        await _cancel_scheduler_task(supervisor_task)
    finally:
        if getattr(app.state, "scheduler_supervisor_task", None) is supervisor_task:
            app.state.scheduler_supervisor_task = None
        _set_scheduler_runtime_snapshot(
            app,
            expected=True,
            status="stopped",
            reason="application_shutdown",
        )


@asynccontextmanager
async def app_lifespan(app: FastAPI):
    logger.info("Starting Application...")

    _verify_google_vision_credentials()
    await _verify_private_attachment_storage()
    await _bootstrap_database()
    _start_scheduler_supervisor(app)

    try:
        yield
    finally:
        await _stop_scheduler_supervisor(app)
        logger.info("Stopping Application...")
