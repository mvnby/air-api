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
    ProviderFactory,
    SessionFactory,
    wait_or_stop,
)
from services.communications.runtime_state import (
    CommunicationRuntimeControl,
    CommunicationRuntimeMode,
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
        worker_factory: WorkerFactory | None = None,
        dispatch: DispatchCallable = CommunicationOutboxDispatcher.dispatch_next,
    ) -> None:
        self._config = config
        self._session_factory = session_factory
        self._provider_factory = provider_factory
        self._worker_factory = worker_factory or self._default_worker_factory
        self._dispatch = dispatch
        self._provider: CommunicationDeliveryProvider | None = None
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
        )

    async def run(self, stop_event: asyncio.Event) -> None:
        try:
            while not stop_event.is_set():
                worked = await self.run_cycle()
                if not worked:
                    await wait_or_stop(stop_event, self._config.poll_seconds)
        finally:
            await self.close()

    async def run_cycle(self) -> bool:
        control = await self._read_control()
        if control.mode == CommunicationRuntimeMode.OFF:
            await self._close_provider()
            await self._record_status(CommunicationRuntimeStatus.DISABLED)
            return False
        if control.mode == CommunicationRuntimeMode.CANARY:
            # C2 does not guess a canary audience. Until a separate, reviewed
            # selector exists this mode is deliberately a visible no-op.
            await self._close_provider()
            await self._record_status(
                CommunicationRuntimeStatus.PAUSED,
                last_error_code="canary_scope_unconfigured",
            )
            return False

        worker = self._ensure_worker()
        await self._record_status(CommunicationRuntimeStatus.RUNNING)
        dispatch_outcome = await self._dispatch_once()
        delivery_outcome = await worker.run_once()
        worked = dispatch_outcome is not None or delivery_outcome.outcome != "idle"
        await self._record_status(
            CommunicationRuntimeStatus.RUNNING,
            activity=worked,
        )
        return worked

    async def close(self) -> None:
        if self._closed:
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
        self._provider = None
        if provider is None:
            return
        async with asyncio.timeout(self._config.provider_close_seconds):
            await provider.close()
