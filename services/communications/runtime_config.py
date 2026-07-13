from __future__ import annotations

import asyncio
import math
import os
import socket
import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from core.config import settings
from core.runtime_controls import ACTIVE_APP_ROLES, normalize_app_role
from services.communications.delivery_limits import (
    MAX_DELIVERY_LEASE_SECONDS,
    MIN_DELIVERY_LEASE_SECONDS,
)
from services.communications.providers.base import CommunicationDeliveryProvider


class CommunicationRuntimeError(RuntimeError):
    pass


class CommunicationRuntimeLockUnavailable(CommunicationRuntimeError):
    pass


class CommunicationRuntimeLockLost(CommunicationRuntimeError):
    pass


class CommunicationRuntimePrimaryRequired(CommunicationRuntimeError):
    pass


class CommunicationRuntimeShutdownTimeout(CommunicationRuntimeError):
    pass


class CommunicationRuntimeProviderCloseFailed(CommunicationRuntimeError):
    pass


class CommunicationRuntimeStopRequested(CommunicationRuntimeError):
    pass


SessionFactory = Callable[[], AsyncSession]
ProviderFactory = Callable[[], CommunicationDeliveryProvider]
PrimaryProbe = Callable[[SessionFactory], Awaitable[None]]
RuntimeSafetyCheck = Callable[[], Awaitable[None]]


def _default_instance_id() -> str:
    hostname = socket.gethostname().strip() or "unknown"
    return f"{hostname}:{os.getpid()}:{uuid.uuid4().hex}"[:128]


@dataclass(frozen=True)
class CommunicationRuntimeConfig:
    enabled: bool
    app_role: str
    channel: str = "telegram"
    lock_name: str = "mvn:communications:telegram"
    instance_id: str = ""
    poll_seconds: float = 1.0
    heartbeat_seconds: float = 10.0
    lock_retry_seconds: float = 2.0
    lock_check_seconds: float = 3.0
    db_probe_timeout_seconds: float = 5.0
    fencing_seconds: float = 60.0
    shutdown_seconds: float = 15.0
    provider_timeout_seconds: float = 10.0
    provider_close_seconds: float = 5.0
    lease_seconds: int = 90

    def __post_init__(self) -> None:
        object.__setattr__(self, "app_role", normalize_app_role(self.app_role))
        object.__setattr__(self, "channel", str(self.channel or "").strip().lower())
        object.__setattr__(self, "lock_name", str(self.lock_name or "").strip())
        if not self.instance_id:
            object.__setattr__(self, "instance_id", _default_instance_id())
        else:
            object.__setattr__(self, "instance_id", self.instance_id.strip())
        if not self.channel or len(self.channel) > 32:
            raise ValueError("Communication runtime channel is invalid")
        if not self.lock_name or len(self.lock_name) > 200:
            raise ValueError("Communication runtime lock name is invalid")
        if not self.instance_id.strip() or len(self.instance_id) > 128:
            raise ValueError("Communication runtime instance ID is invalid")
        duration_fields = (
            "poll_seconds",
            "heartbeat_seconds",
            "lock_retry_seconds",
            "lock_check_seconds",
            "db_probe_timeout_seconds",
            "fencing_seconds",
            "shutdown_seconds",
            "provider_timeout_seconds",
            "provider_close_seconds",
        )
        for field_name in duration_fields:
            value = float(getattr(self, field_name))
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{field_name} must be finite and greater than zero")
            object.__setattr__(self, field_name, value)
        if self.provider_timeout_seconds < 1 or self.provider_timeout_seconds > 60:
            raise ValueError("provider_timeout_seconds must be between 1 and 60")
        handoff_window = (
            self.lock_check_seconds
            # One probe may already hold the serialized advisory connection
            # when the monitor wakes, followed by lock, primary and state
            # checks. Budget all four bounded database probe windows.
            + (4 * self.db_probe_timeout_seconds)
            + self.shutdown_seconds
            + self.provider_timeout_seconds
            + self.provider_close_seconds
        )
        if self.fencing_seconds <= handoff_window:
            raise ValueError(
                "fencing_seconds must be strictly greater than the worst-case "
                "ownership detection and shutdown window"
            )
        lease_seconds = float(self.lease_seconds)
        if (
            not math.isfinite(lease_seconds)
            or not MIN_DELIVERY_LEASE_SECONDS
            <= lease_seconds
            <= MAX_DELIVERY_LEASE_SECONDS
        ):
            raise ValueError(
                "lease_seconds must be between "
                f"{MIN_DELIVERY_LEASE_SECONDS} and "
                f"{MAX_DELIVERY_LEASE_SECONDS}"
            )
        if not lease_seconds.is_integer():
            raise ValueError("lease_seconds must be a whole number")
        # From the database timestamp used by the pre-send renewal, budget its
        # remaining transaction, an in-flight monitor lock probe plus the three
        # action-fence probes, a possible heartbeat-renewal teardown, and the
        # terminal result transaction. The provider call is bounded separately.
        lease_work_window = self.provider_timeout_seconds + (
            7 * self.db_probe_timeout_seconds
        )
        if lease_seconds <= lease_work_window:
            raise ValueError(
                "lease_seconds must be strictly greater than the worst-case "
                "provider and delivery database operation window"
            )
        object.__setattr__(self, "lease_seconds", int(lease_seconds))

    @property
    def deployment_enabled(self) -> bool:
        return bool(self.enabled) and self.app_role in ACTIVE_APP_ROLES

    @classmethod
    def from_settings(cls) -> "CommunicationRuntimeConfig":
        return cls(
            enabled=settings.COMMUNICATIONS_WORKER_ENABLED,
            app_role=settings.APP_ROLE,
            poll_seconds=settings.COMMUNICATIONS_WORKER_POLL_SECONDS,
            heartbeat_seconds=settings.COMMUNICATIONS_WORKER_HEARTBEAT_SECONDS,
            lock_retry_seconds=settings.COMMUNICATIONS_WORKER_LOCK_RETRY_SECONDS,
            lock_check_seconds=settings.COMMUNICATIONS_WORKER_LOCK_CHECK_SECONDS,
            db_probe_timeout_seconds=(
                settings.COMMUNICATIONS_WORKER_DB_PROBE_TIMEOUT_SECONDS
            ),
            fencing_seconds=settings.COMMUNICATIONS_WORKER_FENCING_SECONDS,
            shutdown_seconds=settings.COMMUNICATIONS_WORKER_SHUTDOWN_SECONDS,
            provider_timeout_seconds=(
                settings.COMMUNICATIONS_WORKER_PROVIDER_TIMEOUT_SECONDS
            ),
            provider_close_seconds=settings.COMMUNICATIONS_WORKER_PROVIDER_CLOSE_SECONDS,
            lease_seconds=settings.COMMUNICATIONS_WORKER_LEASE_SECONDS,
        )


async def assert_primary_writable(session_factory: SessionFactory) -> None:
    """Fail closed unless the target is writable PostgreSQL primary."""

    async with session_factory() as session:
        dialect = session.get_bind().dialect.name
        if dialect != "postgresql":
            raise CommunicationRuntimePrimaryRequired(
                f"communications runtime requires PostgreSQL, got {dialect!r}"
            )
        row = (
            await session.execute(
                text(
                    "SELECT pg_is_in_recovery() AS in_recovery, "
                    "current_setting('transaction_read_only') AS read_only"
                )
            )
        ).one()
    if bool(row.in_recovery) or str(row.read_only).strip().lower() != "off":
        raise CommunicationRuntimePrimaryRequired(
            "communications runtime requires a writable PostgreSQL primary"
        )


async def wait_or_stop(stop_event: asyncio.Event, seconds: float) -> bool:
    if stop_event.is_set():
        return True
    if seconds <= 0:
        await asyncio.sleep(0)
        return stop_event.is_set()
    try:
        await asyncio.wait_for(stop_event.wait(), timeout=seconds)
    except TimeoutError:
        return False
    return True


def safe_error_type(error: BaseException) -> str:
    raw_name = type(error).__name__
    normalized = "".join(
        character if character.isalnum() or character == "_" else "_"
        for character in raw_name
    )
    return (normalized or "Exception")[:64]
