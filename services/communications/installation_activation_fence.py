"""Commit-order fence for installation event enqueue and activation."""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT = (
    "crm.installation_estimate_lead.created"
)
INSTALLATION_ACTIVATION_FENCE_LOCK = (
    "mvn:communications:installation-estimate-activation"
)
INSTALLATION_ENQUEUE_FENCE_TIMEOUT_SECONDS = 1.0
INSTALLATION_ENQUEUE_FENCE_POLL_SECONDS = 0.02


class InstallationEventEnqueueFenceBusy(RuntimeError):
    """A bounded target enqueue could not cross an active control fence."""

    error_code = "installation_activation_fence_busy"

    def __init__(self) -> None:
        super().__init__(self.error_code)


async def acquire_installation_enqueue_fence(
    session: AsyncSession,
) -> datetime:
    """Take a shared fence and return the authoritative event creation time."""

    if session.get_bind().dialect.name != "postgresql":
        return datetime.now(timezone.utc)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + INSTALLATION_ENQUEUE_FENCE_TIMEOUT_SECONDS
    while True:
        acquired = await session.scalar(
            text(
                "SELECT pg_try_advisory_xact_lock_shared("
                "hashtext(:lock_name))"
            ),
            {"lock_name": INSTALLATION_ACTIVATION_FENCE_LOCK},
        )
        if acquired is True:
            break
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise InstallationEventEnqueueFenceBusy()
        await asyncio.sleep(
            min(INSTALLATION_ENQUEUE_FENCE_POLL_SECONDS, remaining)
        )
    value = await session.scalar(text("SELECT clock_timestamp()"))
    if not isinstance(value, datetime):
        raise TypeError("Database clock did not return a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def acquire_installation_activation_fence(
    session: AsyncSession,
) -> bool:
    """Try to take the exclusive activation side of the commit-order fence.

    Normal event enqueues share the lock and remain concurrent with each other.
    A successful activation attempt temporarily excludes later timestamp
    creation until its control transaction commits.

    The operator command must never hang behind a stalled request transaction,
    so this is deliberately a non-blocking attempt. The caller reports a fixed
    blocker and can be rerun after the in-flight enqueue finishes.
    """

    if session.get_bind().dialect.name != "postgresql":
        return True
    acquired = await session.scalar(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:lock_name))"),
        {"lock_name": INSTALLATION_ACTIVATION_FENCE_LOCK},
    )
    return acquired is True
