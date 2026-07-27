import asyncio
from datetime import datetime, timezone

from services.communications.processing_scope import CommunicationProcessingScope
from services.communications.runtime_state import (
    CommunicationRuntimeMode,
    CommunicationRuntimeStateService,
)


async def allow_safety(_scope: CommunicationProcessingScope) -> None:
    return None


async def instant_fencing(
    stop_event: asyncio.Event,
    _seconds: float,
) -> bool:
    return stop_event.is_set()


async def set_runtime_mode_for_test(
    session,
    *,
    channel: str,
    mode: CommunicationRuntimeMode,
    canary_run_id: str | None = None,
):
    """Use the typed public path except when a test needs an armed all scope."""

    if mode != CommunicationRuntimeMode.ALL:
        return await CommunicationRuntimeStateService.set_mode(
            session,
            channel=channel,
            mode=mode,
            canary_run_id=canary_run_id,
        )
    state = await CommunicationRuntimeStateService.ensure_state(
        session,
        channel=channel,
    )
    state.mode = CommunicationRuntimeMode.ALL.value
    state.canary_run_id = None
    state.control_revision = int(state.control_revision) + 1
    state.installation_estimate_watermark_at = (
        state.installation_estimate_watermark_at
        or datetime(2000, 1, 1, tzinfo=timezone.utc)
    )
    session.add(state)
    await session.flush()
    return CommunicationRuntimeStateService._to_control(state)
