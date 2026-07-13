from __future__ import annotations

import asyncio
import logging
import signal

from core.app_observability import init_sentry
from core.config import settings
from core.database import async_session_maker
from core.logger import setup_logging
from services.communications.providers.base import CommunicationDeliveryProvider
from services.communications.providers.telegram import TelegramDeliveryProvider
from services.communications.runtime_config import (
    CommunicationRuntimeConfig,
    CommunicationRuntimeError,
    CommunicationRuntimeLockLost,
    CommunicationRuntimeLockUnavailable,
    CommunicationRuntimePrimaryRequired,
    CommunicationRuntimeProviderCloseFailed,
    CommunicationRuntimeShutdownTimeout,
    ProviderFactory,
    RuntimeSafetyCheck,
    SessionFactory,
    assert_primary_writable,
    safe_error_type,
)
from services.communications.runtime_pipeline import CommunicationRuntimePipeline
from services.communications.runtime_supervisor import CommunicationRuntimeSupervisor


logger = logging.getLogger(__name__)

__all__ = [
    "CommunicationRuntimeConfig",
    "CommunicationRuntimeError",
    "CommunicationRuntimeLockLost",
    "CommunicationRuntimeLockUnavailable",
    "CommunicationRuntimePipeline",
    "CommunicationRuntimePrimaryRequired",
    "CommunicationRuntimeProviderCloseFailed",
    "CommunicationRuntimeShutdownTimeout",
    "CommunicationRuntimeSupervisor",
    "assert_primary_writable",
    "run_communications_runtime",
]


def _default_provider_factory(config: CommunicationRuntimeConfig) -> ProviderFactory:
    def build() -> CommunicationDeliveryProvider:
        return TelegramDeliveryProvider(
            token=settings.BOT_TOKEN,
            request_timeout_seconds=config.provider_timeout_seconds,
        )

    return build


async def run_communications_runtime(
    *,
    stop_event: asyncio.Event | None = None,
    config: CommunicationRuntimeConfig | None = None,
    session_factory: SessionFactory = async_session_maker,
    provider_factory: ProviderFactory | None = None,
    wait_when_disabled: bool = True,
) -> None:
    effective_config = config or CommunicationRuntimeConfig.from_settings()
    effective_stop = stop_event or asyncio.Event()
    if not effective_config.deployment_enabled:
        logger.info(
            "Communications runtime is dormant enabled=%s app_role=%s",
            effective_config.enabled,
            effective_config.app_role,
        )
        if wait_when_disabled:
            await effective_stop.wait()
        return

    effective_provider_factory = provider_factory or _default_provider_factory(
        effective_config
    )

    def build_pipeline(safety_check: RuntimeSafetyCheck) -> CommunicationRuntimePipeline:
        return CommunicationRuntimePipeline(
            config=effective_config,
            session_factory=session_factory,
            provider_factory=effective_provider_factory,
            safety_check=safety_check,
        )

    supervisor = CommunicationRuntimeSupervisor(
        config=effective_config,
        session_factory=session_factory,
        pipeline_factory=build_pipeline,
    )
    await supervisor.run(effective_stop)


async def _run_process() -> None:
    stop_event = asyncio.Event()
    loop = asyncio.get_running_loop()
    for signum in (signal.SIGTERM, signal.SIGINT):
        try:
            loop.add_signal_handler(signum, stop_event.set)
        except NotImplementedError:  # pragma: no cover - non-POSIX fallback
            pass
    await run_communications_runtime(stop_event=stop_event)


def main() -> int:
    setup_logging(session_log_file="logs/communications-worker.log")
    init_sentry()
    try:
        asyncio.run(_run_process())
    except KeyboardInterrupt:
        return 0
    except Exception as error:
        logger.error(
            "Communications runtime terminated "
            "error_code=runtime_terminated error_type=%s",
            safe_error_type(error),
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
