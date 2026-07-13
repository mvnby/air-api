from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from time import monotonic
from typing import Any, Protocol

from services.communications.delivery_worker import (
    CommunicationDeliveryWorker,
    DeliveryRunOutcome,
)
from services.communications.dispatcher import CommunicationOutboxDispatcher
from services.communications.providers.base import CommunicationDeliveryProvider
from services.communications.runtime_config import (
    CommunicationRuntimeConfig,
    CommunicationRuntimeError,
    CommunicationRuntimeProviderCloseFailed,
    CommunicationRuntimeStopRequested,
    ProviderFactory,
    RuntimeSafetyCheck,
    SessionFactory,
    wait_or_stop,
)
from services.communications.runtime_state import (
    CommunicationRuntimeControl,
    CommunicationRuntimeMode,
    CommunicationRuntimeModeBlocked,
    CommunicationRuntimeStateService,
    CommunicationRuntimeStatus,
)


class _DeliveryWorker(Protocol):
    async def run_once(self) -> DeliveryRunOutcome: ...


WorkerFactory = Callable[[CommunicationDeliveryProvider], _DeliveryWorker]
DispatchCallable = Callable[..., Awaitable[Any]]


class CommunicationRuntimePipeline:
    """Single-concurrency dispatch/delivery loop owned by the supervisor."""

    def __init__(
        self,
        *,
        config: CommunicationRuntimeConfig,
        session_factory: SessionFactory,
        provider_factory: ProviderFactory,
        safety_check: RuntimeSafetyCheck,
        worker_factory: WorkerFactory | None = None,
        dispatch: DispatchCallable = CommunicationOutboxDispatcher.dispatch_next,
    ) -> None:
        self._config = config
        self._session_factory = session_factory
        self._provider_factory = provider_factory
        self._safety_check = safety_check
        self._worker_factory = worker_factory or self._default_worker_factory
        self._dispatch = dispatch
        self._provider: CommunicationDeliveryProvider | None = None
        self._provider_close_task: asyncio.Task[None] | None = None
        self._worker: _DeliveryWorker | None = None
        self._last_status: CommunicationRuntimeStatus | None = None
        self._last_error_code: str | None = None
        self._last_heartbeat_monotonic = 0.0
        self._closed = False

    def _default_worker_factory(
        self,
        provider: CommunicationDeliveryProvider,
    ) -> CommunicationDeliveryWorker:
        return CommunicationDeliveryWorker(
            session_factory=self._session_factory,
            provider=provider,
            worker_id=self._config.instance_id,
            lease_seconds=self._config.lease_seconds,
            safety_check=self._safety_check,
            db_operation_timeout_seconds=self._config.db_probe_timeout_seconds,
        )

    async def run(self, stop_event: asyncio.Event) -> None:
        try:
            while not stop_event.is_set():
                worked = await self.run_cycle()
                if not worked:
                    await wait_or_stop(stop_event, self._config.poll_seconds)
        except CommunicationRuntimeStopRequested:
            if not stop_event.is_set():
                raise
        finally:
            await self.close()

    async def run_cycle(self) -> bool:
        control = await self._read_control()
        if control.mode != CommunicationRuntimeMode.ALL:
            await self._pause_for_mode(control.mode)
            return False

        try:
            await self._safety_check()
            await self._record_status(CommunicationRuntimeStatus.RUNNING)
            # The status write above yields control. Re-fence at the last possible
            # point before the dispatcher can lock or mutate an outbox event.
            await self._safety_check()
            dispatch_outcome = await self._dispatch_once()
            # Dispatch may set the process stop signal or ownership may disappear
            # while its transaction commits. Do not even construct a provider until
            # this second handoff fence succeeds.
            await self._safety_check()
            worker = self._ensure_worker()
            delivery_outcome = await worker.run_once()
        except CommunicationRuntimeModeBlocked as blocked:
            await self._pause_for_mode(blocked.mode)
            return False
        worked = dispatch_outcome is not None or delivery_outcome.outcome != "idle"
        await self._record_status(
            CommunicationRuntimeStatus.RUNNING,
            activity=worked,
        )
        return worked

    async def _pause_for_mode(self, mode: CommunicationRuntimeMode) -> None:
        await self._close_provider()
        if mode == CommunicationRuntimeMode.OFF:
            await self._record_status(CommunicationRuntimeStatus.DISABLED)
            return
        if mode == CommunicationRuntimeMode.CANARY:
            # C2 does not guess a canary audience. Until a separate, reviewed
            # selector exists this mode is deliberately a visible no-op.
            await self._record_status(
                CommunicationRuntimeStatus.PAUSED,
                last_error_code="canary_scope_unconfigured",
            )
            return
        raise CommunicationRuntimeError("communications runtime mode fence is invalid")

    async def close(self) -> None:
        if self._closed and self._provider is None:
            return
        self._closed = True
        await self._close_provider()

    async def _read_control(self) -> CommunicationRuntimeControl:
        async with self._session_factory() as session:
            return await CommunicationRuntimeStateService.read_owned_control(
                session,
                channel=self._config.channel,
                instance_id=self._config.instance_id,
            )

    async def _record_status(
        self,
        status: CommunicationRuntimeStatus,
        *,
        last_error_code: str | None = None,
        activity: bool = False,
    ) -> None:
        now = monotonic()
        heartbeat_due = (
            now - self._last_heartbeat_monotonic
            >= self._config.heartbeat_seconds
        )
        changed = status != self._last_status or last_error_code != self._last_error_code
        if not (changed or heartbeat_due or activity):
            return
        async with self._session_factory() as session:
            await CommunicationRuntimeStateService.record_status(
                session,
                channel=self._config.channel,
                instance_id=self._config.instance_id,
                status=status,
                last_error_code=last_error_code,
                activity=activity,
            )
            await session.commit()
        self._last_status = status
        self._last_error_code = last_error_code
        self._last_heartbeat_monotonic = now

    def _ensure_worker(self) -> _DeliveryWorker:
        if self._worker is not None:
            return self._worker
        if self._closed:
            raise CommunicationRuntimeError("communications pipeline is closed")
        provider = self._provider_factory()
        self._provider = provider
        if provider.channel != self._config.channel:
            raise CommunicationRuntimeError(
                "communications provider channel does not match runtime channel"
            )
        self._worker = self._worker_factory(provider)
        return self._worker

    async def _dispatch_once(self) -> Any:
        async with self._session_factory() as session:
            try:
                outcome = await self._dispatch(
                    session,
                    dispatcher_id=self._config.instance_id,
                )
                await session.commit()
                return outcome
            except BaseException:
                await session.rollback()
                raise

    async def _close_provider(self) -> None:
        provider = self._provider
        self._worker = None
        if provider is None:
            return
        for _attempt in range(2):
            if await self._close_provider_once(provider):
                # Retain the strong provider reference until close positively
                # completes. A replacement runtime must never start while the
                # previous provider resource is still live or indeterminate.
                self._provider = None
                return
        raise CommunicationRuntimeProviderCloseFailed(
            "communications provider did not close after bounded retries"
        )

    async def _close_provider_once(
        self,
        provider: CommunicationDeliveryProvider,
    ) -> bool:
        close_task = self._provider_close_task
        if close_task is None:
            close_task = asyncio.create_task(
                provider.close(),
                name="communications-provider-close",
            )
            self._provider_close_task = close_task
        finished, pending = await asyncio.wait(
            {close_task},
            timeout=self._config.provider_close_seconds,
        )
        if pending:
            close_task.cancel()
            finished, pending = await asyncio.wait(
                {close_task},
                timeout=self._config.provider_close_seconds,
            )
            if pending:
                raise CommunicationRuntimeProviderCloseFailed(
                    "communications provider close ignored cancellation"
                )

        completed_task = next(iter(finished))
        self._provider_close_task = None
        if completed_task.cancelled():
            return False
        try:
            completed_task.result()
        except BaseException:
            return False
        return True
