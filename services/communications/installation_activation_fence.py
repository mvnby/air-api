"""Commit-order fence for activated tenant website communications."""

import asyncio
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from services.communications.tenant_website_events import (
    INSTALLATION_ESTIMATE_LEAD_CREATED_EVENT,
)

WEBSITE_COMMUNICATION_ACTIVATION_FENCE_LOCK = (
    # Preserve the deployed lock identity across rolling upgrades. Only its
    # reviewed event allowlist widened; changing the lock key would let old and
    # new replicas cross the activation boundary independently.
    "mvn:communications:installation-estimate-activation"
)
WEBSITE_ENQUEUE_FENCE_TIMEOUT_SECONDS = 1.0
WEBSITE_ENQUEUE_FENCE_POLL_SECONDS = 0.02

# Compatibility exports for the existing operator command and tests. Their
# semantics now cover the whole reviewed tenant website event allowlist.
INSTALLATION_ACTIVATION_FENCE_LOCK = WEBSITE_COMMUNICATION_ACTIVATION_FENCE_LOCK
INSTALLATION_ENQUEUE_FENCE_TIMEOUT_SECONDS = WEBSITE_ENQUEUE_FENCE_TIMEOUT_SECONDS
INSTALLATION_ENQUEUE_FENCE_POLL_SECONDS = WEBSITE_ENQUEUE_FENCE_POLL_SECONDS


class InstallationEventEnqueueFenceBusy(RuntimeError):
    """A bounded target enqueue could not cross an active control fence."""

    error_code = "installation_activation_fence_busy"

    def __init__(self) -> None:
        super().__init__(self.error_code)


WebsiteCommunicationEnqueueFenceBusy = InstallationEventEnqueueFenceBusy


async def acquire_website_communication_enqueue_fence(
    session: AsyncSession,
) -> datetime:
    """Take a shared fence and return the authoritative event creation time."""

    if session.get_bind().dialect.name != "postgresql":
        value = await session.scalar(text("SELECT CURRENT_TIMESTAMP"))
        if isinstance(value, str):
            value = datetime.fromisoformat(value)
        if not isinstance(value, datetime):
            raise TypeError("Database clock did not return a datetime")
        if value.tzinfo is None or value.utcoffset() is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    loop = asyncio.get_running_loop()
    deadline = loop.time() + WEBSITE_ENQUEUE_FENCE_TIMEOUT_SECONDS
    while True:
        acquired = await session.scalar(
            text(
                "SELECT pg_try_advisory_xact_lock_shared("
                "hashtext(:lock_name))"
            ),
            {"lock_name": WEBSITE_COMMUNICATION_ACTIVATION_FENCE_LOCK},
        )
        if acquired is True:
            break
        remaining = deadline - loop.time()
        if remaining <= 0:
            raise InstallationEventEnqueueFenceBusy()
        await asyncio.sleep(
            min(WEBSITE_ENQUEUE_FENCE_POLL_SECONDS, remaining)
        )
    value = await session.scalar(text("SELECT clock_timestamp()"))
    if not isinstance(value, datetime):
        raise TypeError("Database clock did not return a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


async def acquire_website_communication_activation_fence(
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
        {"lock_name": WEBSITE_COMMUNICATION_ACTIVATION_FENCE_LOCK},
    )
    return acquired is True


async def acquire_installation_enqueue_fence(
    session: AsyncSession,
) -> datetime:
    return await acquire_website_communication_enqueue_fence(session)


async def acquire_installation_activation_fence(
    session: AsyncSession,
) -> bool:
    return await acquire_website_communication_activation_fence(session)
