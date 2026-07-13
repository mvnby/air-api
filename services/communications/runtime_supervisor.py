from __future__ import annotations

import asyncio
import logging
import os
import signal
from collections.abc import Awaitable, Callable
from typing import Protocol

from services.communications.runtime_config import (
    CommunicationRuntimeConfig,
    CommunicationRuntimeError,
    CommunicationRuntimeLockLost,
    CommunicationRuntimeLockUnavailable,
    CommunicationRuntimePrimaryRequired,
    CommunicationRuntimeProviderCloseFailed,
    CommunicationRuntimeShutdownTimeout,
    CommunicationRuntimeStopRequested,
    PrimaryProbe,
    RuntimeSafetyCheck,
    SessionFactory,
    assert_primary_writable,
    safe_error_type,
    wait_or_stop,
)
from services.communications.runtime_state import (
    CommunicationRuntimeStateOwnershipLost,
    CommunicationRuntimeStateService,
    CommunicationRuntimeStatus,
)
from services.runtime_lock_service import RuntimeLock, RuntimeLockService


logger = logging.getLogger(__name__)


class RuntimePipeline(Protocol):
    async def run(self, stop_event: asyncio.Event) -> None: ...


class CommunicationRuntimeSupervisor:
    """Own the required advisory lock and bounded process lifecycle."""

    def __init__(
        self,
        *,
        config: CommunicationRuntimeConfig,
        session_factory: SessionFactory,
        pipeline_factory: Callable[[RuntimeSafetyCheck], RuntimePipeline],
        primary_probe: PrimaryProbe = assert_primary_writable,
        lock_service: type[RuntimeLockService] = RuntimeLockService,
        hard_stop: Callable[[], None] | None = None,
        fencing_wait: Callable[
            [asyncio.Event, float], Awaitable[bool]
        ] = wait_or_stop,
    ) -> None:
        self._config = config
        self._session_factory = session_factory
        self._pipeline_factory = pipeline_factory
        self._primary_probe = primary_probe
        self._lock_service = lock_service
        self._hard_stop = hard_stop or self._kill_process
        self._fencing_wait = fencing_wait
        self._lock_probe_mutex = asyncio.Lock()

    @staticmethod
    def _kill_process() -> None:
        os.kill(os.getpid(), signal.SIGKILL)

    async def run(self, stop_event: asyncio.Event) -> None:
        runtime_lock: RuntimeLock | None = None
        owned = False
        release_allowed = True
        terminal_error: BaseException | None = None
        try:
            runtime_lock = await self._acquire_lock(stop_event)
            if runtime_lock is None or stop_event.is_set():
                return
            await self._probe_primary()
            if stop_event.is_set():
                return
            await self._take_ownership()
            owned = True

            if await self._fencing_wait(stop_event, self._config.fencing_seconds):
                return
            if not await self._lock_is_held(runtime_lock):
                raise CommunicationRuntimeLockLost(
                    "communications advisory lock was lost during fencing"
                )
            await self._probe_primary()

            pipeline = self._pipeline_factory(
                lambda: self._assert_safe_to_work(stop_event, runtime_lock)
            )
            work_task = asyncio.create_task(
                pipeline.run(stop_event),
                name="communications-work-loop",
            )
            monitor_task = asyncio.create_task(
                self._monitor_ownership(stop_event, runtime_lock),
                name="communications-ownership-monitor",
            )
            stop_task = asyncio.create_task(
                stop_event.wait(),
                name="communications-stop-waiter",
            )
            try:
                done, _ = await asyncio.wait(
                    {work_task, monitor_task, stop_task},
                    return_when=asyncio.FIRST_COMPLETED,
                )
            except asyncio.CancelledError as cancellation:
                # Treat task cancellation exactly like SIGTERM: stop intake,
                # drain provider work, persist state, then release ownership.
                done = set()
                terminal_error = cancellation
            monitor_failure: BaseException | None = None
            if monitor_task in done:
                if monitor_task.cancelled():
                    monitor_failure = CommunicationRuntimeError(
                        "communications ownership monitor was cancelled"
                    )
                else:
                    monitor_failure = monitor_task.exception()
                    if monitor_failure is None and not stop_event.is_set():
                        monitor_failure = CommunicationRuntimeError(
                            "communications ownership monitor stopped unexpectedly"
                        )
            if monitor_failure is not None:
                # Ownership loss is a fail-stop event, not a graceful drain.
                # Cancel the active claim/provider task before any state write
                # or other await can widen the failover overlap window.
                terminal_error = monitor_failure
                stop_event.set()
                work_task.cancel()
            elif work_task in done and not stop_event.is_set():
                if work_task.cancelled():
                    terminal_error = CommunicationRuntimeError(
                        "communications work loop was cancelled unexpectedly"
                    )
                else:
                    terminal_error = work_task.exception() or CommunicationRuntimeError(
                        "communications work loop stopped unexpectedly"
                    )

            stop_event.set()
            await self._best_effort_status(CommunicationRuntimeStatus.STOPPING)
            drained, pending = await asyncio.wait(
                {work_task, monitor_task},
                timeout=self._config.shutdown_seconds,
            )
            if pending:
                release_allowed = False
                await self._best_effort_status(
                    CommunicationRuntimeStatus.FAULTED,
                    last_error_code="shutdown_timeout",
                )
                logger.critical(
                    "Communications runtime shutdown deadline exceeded; "
                    "advisory lock will not be released "
                    "error_code=shutdown_timeout instance_id=%s",
                    self._config.instance_id,
                )
                self._hard_stop()
                raise CommunicationRuntimeShutdownTimeout(
                    "communications runtime hard-stop callback returned"
                )

            results = await asyncio.gather(*drained, return_exceptions=True)
            for result in results:
                if isinstance(result, CommunicationRuntimeProviderCloseFailed):
                    terminal_error = result
                elif isinstance(result, BaseException) and terminal_error is None:
                    terminal_error = result
            stop_task.cancel()
            await asyncio.gather(stop_task, return_exceptions=True)
            if isinstance(
                terminal_error,
                CommunicationRuntimeProviderCloseFailed,
            ):
                release_allowed = False
                await self._best_effort_status(
                    CommunicationRuntimeStatus.FAULTED,
                    last_error_code="provider_close_failed",
                )
                logger.critical(
                    "Communications provider close failed; fail-stop required "
                    "error_code=provider_close_failed instance_id=%s",
                    self._config.instance_id,
                )
                self._hard_stop()
                raise CommunicationRuntimeShutdownTimeout(
                    "communications provider-close hard-stop callback returned"
                )
            if terminal_error is not None:
                raise terminal_error
        except BaseException as exc:
            terminal_error = exc
            raise
        finally:
            if owned:
                await self._record_terminal_status(terminal_error)
            # Releasing the lock is intentionally the final awaited lifecycle
            # action. On a missed shutdown deadline it remains pinned until the
            # process is forcibly terminated by the operating system.
            if runtime_lock is not None and release_allowed:
                await self._release_lock(runtime_lock)

    async def _record_terminal_status(
        self,
        terminal_error: BaseException | None,
    ) -> None:
        if terminal_error is None or isinstance(
            terminal_error,
            asyncio.CancelledError,
        ):
            await self._best_effort_status(CommunicationRuntimeStatus.STOPPED)
        elif not isinstance(terminal_error, CommunicationRuntimeShutdownTimeout):
            await self._best_effort_status(
                CommunicationRuntimeStatus.FAULTED,
                last_error_code=safe_error_type(terminal_error),
            )

    async def _release_lock(self, runtime_lock: RuntimeLock) -> None:
        release_task = asyncio.create_task(
            runtime_lock.release(),
            name="communications-lock-release",
        )
        released, pending = await asyncio.wait(
            {release_task},
            timeout=self._config.db_probe_timeout_seconds,
        )
        if pending:
            logger.critical(
                "Communications advisory lock release deadline exceeded "
                "error_code=lock_release_timeout instance_id=%s",
                self._config.instance_id,
            )
            self._hard_stop()
            raise CommunicationRuntimeShutdownTimeout(
                "communications lock release hard-stop callback returned"
            )
        await next(iter(released))

    async def _acquire_lock(
        self,
        stop_event: asyncio.Event,
    ) -> RuntimeLock | None:
        while not stop_event.is_set():
            try:
                async with asyncio.timeout(self._config.db_probe_timeout_seconds):
                    lock = await self._lock_service.try_acquire(
                        self._session_factory,
                        self._config.lock_name,
                        required=True,
                    )
            except TimeoutError:
                logger.warning(
                    "Communications advisory lock acquisition timed out "
                    "error_code=lock_acquire_timeout instance_id=%s",
                    self._config.instance_id,
                )
                await wait_or_stop(stop_event, self._config.lock_retry_seconds)
                continue
            if lock.acquired:
                logger.info(
                    "Communications runtime acquired required advisory lock "
                    "channel=%s instance_id=%s",
                    self._config.channel,
                    self._config.instance_id,
                )
                return lock
            if not lock.retryable:
                raise CommunicationRuntimeLockUnavailable(lock.reason)
            await wait_or_stop(stop_event, self._config.lock_retry_seconds)
        return None

    async def _take_ownership(self) -> None:
        try:
            async with asyncio.timeout(self._config.db_probe_timeout_seconds):
                async with self._session_factory() as session:
                    await CommunicationRuntimeStateService.take_ownership(
                        session,
                        channel=self._config.channel,
                        instance_id=self._config.instance_id,
                    )
                    await session.commit()
        except TimeoutError as exc:
            raise CommunicationRuntimeError(
                "communications state ownership update timed out"
            ) from exc

    async def _probe_primary(self) -> None:
        try:
            async with asyncio.timeout(self._config.db_probe_timeout_seconds):
                await self._primary_probe(self._session_factory)
        except TimeoutError as exc:
            raise CommunicationRuntimePrimaryRequired(
                "communications writable-primary probe timed out"
            ) from exc

    async def _assert_safe_to_work(
        self,
        stop_event: asyncio.Event,
        runtime_lock: RuntimeLock,
    ) -> None:
        if stop_event.is_set():
            raise CommunicationRuntimeStopRequested(
                "communications runtime stop was requested"
            )
        if not await self._lock_is_held(runtime_lock):
            raise CommunicationRuntimeLockLost(
                "communications advisory lock was lost before work"
            )
        await self._probe_primary()
        await self._verify_active_control()
        if stop_event.is_set():
            raise CommunicationRuntimeStopRequested(
                "communications runtime stop was requested"
            )

    async def _lock_is_held(self, runtime_lock: RuntimeLock) -> bool:
        try:
            async with self._lock_probe_mutex:
                async with asyncio.timeout(self._config.db_probe_timeout_seconds):
                    return await runtime_lock.is_held()
        except TimeoutError as exc:
            raise CommunicationRuntimeLockLost(
                "communications advisory lock liveness probe timed out"
            ) from exc

    async def _monitor_ownership(
        self,
        stop_event: asyncio.Event,
        runtime_lock: RuntimeLock,
    ) -> None:
        while not await wait_or_stop(stop_event, self._config.lock_check_seconds):
            if not await self._lock_is_held(runtime_lock):
                raise CommunicationRuntimeLockLost(
                    "communications advisory lock was lost"
                )
            await self._probe_primary()
            await self._verify_state_ownership()

    async def _verify_state_ownership(self) -> None:
        try:
            async with asyncio.timeout(self._config.db_probe_timeout_seconds):
                async with self._session_factory() as session:
                    await CommunicationRuntimeStateService.read_owned_control(
                        session,
                        channel=self._config.channel,
                        instance_id=self._config.instance_id,
                    )
        except TimeoutError as exc:
            raise CommunicationRuntimeStateOwnershipLost(
                "communications state ownership probe timed out"
            ) from exc

    async def _verify_active_control(self) -> None:
        try:
            async with asyncio.timeout(self._config.db_probe_timeout_seconds):
                async with self._session_factory() as session:
                    await CommunicationRuntimeStateService.read_active_owned_control(
                        session,
                        channel=self._config.channel,
                        instance_id=self._config.instance_id,
                    )
        except TimeoutError as exc:
            raise CommunicationRuntimeStateOwnershipLost(
                "communications active control probe timed out"
            ) from exc

    async def _best_effort_status(
        self,
        status: CommunicationRuntimeStatus,
        *,
        last_error_code: str | None = None,
    ) -> None:
        try:
            async with asyncio.timeout(self._config.db_probe_timeout_seconds):
                async with self._session_factory() as session:
                    await CommunicationRuntimeStateService.record_status(
                        session,
                        channel=self._config.channel,
                        instance_id=self._config.instance_id,
                        status=status,
                        last_error_code=last_error_code,
                    )
                    await session.commit()
        except CommunicationRuntimeStateOwnershipLost:
            logger.error(
                "Communications runtime state ownership was lost "
                "error_code=runtime_state_ownership_lost instance_id=%s",
                self._config.instance_id,
            )
        except Exception as error:
            logger.error(
                "Communications runtime lifecycle state write failed "
                "error_code=runtime_state_write_failed error_type=%s instance_id=%s",
                safe_error_type(error),
                self._config.instance_id,
            )
