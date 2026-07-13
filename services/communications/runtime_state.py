from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from models import CommunicationRuntimeState


class CommunicationRuntimeMode(str, Enum):
    OFF = "off"
    CANARY = "canary"
    ALL = "all"


class CommunicationRuntimeStatus(str, Enum):
    STOPPED = "stopped"
    FENCING = "fencing"
    DISABLED = "disabled"
    PAUSED = "paused"
    RUNNING = "running"
    STOPPING = "stopping"
    FAULTED = "faulted"


class CommunicationRuntimeStateOwnershipLost(RuntimeError):
    pass


class CommunicationRuntimeModeBlocked(RuntimeError):
    def __init__(self, mode: CommunicationRuntimeMode) -> None:
        super().__init__("Communication runtime mode does not allow delivery work")
        self.mode = mode


@dataclass(frozen=True)
class CommunicationRuntimeControl:
    channel: str
    mode: CommunicationRuntimeMode
    status: CommunicationRuntimeStatus
    instance_id: str | None
    heartbeat_at: datetime | None


class CommunicationRuntimeStateService:
    """Caller-transactional control and ownership operations.

    Operator-owned ``mode`` is intentionally absent from heartbeat updates.
    Every lifecycle write is fenced by ``instance_id`` so an old process cannot
    overwrite the state of a replacement after losing the advisory lock.
    """

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc)

    @staticmethod
    def _normalize_channel(channel: str) -> str:
        value = str(channel or "").strip().lower()
        if not value or len(value) > 32:
            raise ValueError("Communication runtime channel is invalid")
        return value

    @staticmethod
    def _normalize_instance_id(instance_id: str) -> str:
        value = str(instance_id or "").strip()
        if not value or len(value) > 128:
            raise ValueError("Communication runtime instance ID is invalid")
        return value

    @staticmethod
    def _normalize_error_code(error_code: str | None) -> str | None:
        if error_code is None:
            return None
        value = str(error_code).strip()
        if not value:
            return None
        return value[:100]

    @classmethod
    async def ensure_state(
        cls,
        session: AsyncSession,
        *,
        channel: str,
    ) -> CommunicationRuntimeState:
        normalized_channel = cls._normalize_channel(channel)
        state = await session.get(CommunicationRuntimeState, normalized_channel)
        if state is not None:
            return state
        now = cls._now()
        state = CommunicationRuntimeState(
            channel=normalized_channel,
            mode=CommunicationRuntimeMode.OFF.value,
            status=CommunicationRuntimeStatus.STOPPED.value,
            control_updated_at=now,
            created_at=now,
            updated_at=now,
        )
        session.add(state)
        await session.flush()
        return state

    @classmethod
    async def set_mode(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        mode: CommunicationRuntimeMode | str,
    ) -> CommunicationRuntimeControl:
        normalized_mode = CommunicationRuntimeMode(mode)
        state = await cls.ensure_state(session, channel=channel)
        now = cls._now()
        state.mode = normalized_mode.value
        state.control_updated_at = now
        state.updated_at = now
        await session.flush()
        return cls._to_control(state)

    @classmethod
    async def take_ownership(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        instance_id: str,
    ) -> CommunicationRuntimeControl:
        normalized_channel = cls._normalize_channel(channel)
        normalized_instance_id = cls._normalize_instance_id(instance_id)
        state = await cls.ensure_state(session, channel=normalized_channel)
        if session.get_bind().dialect.name == "postgresql":
            # Re-read while locking the row. The advisory lock serializes normal
            # runtimes; this row lock also protects manual control-plane writes.
            state = await session.get(
                CommunicationRuntimeState,
                normalized_channel,
                populate_existing=True,
                with_for_update=True,
            )
            if state is None:  # pragma: no cover - protected by ensure_state
                raise RuntimeError("Communication runtime state disappeared")
        now = cls._now()
        state.status = CommunicationRuntimeStatus.FENCING.value
        state.instance_id = normalized_instance_id
        state.started_at = now
        state.heartbeat_at = now
        state.last_activity_at = None
        state.last_error_code = None
        state.updated_at = now
        await session.flush()
        return cls._to_control(state)

    @classmethod
    async def read_owned_control(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        instance_id: str,
    ) -> CommunicationRuntimeControl:
        normalized_channel = cls._normalize_channel(channel)
        normalized_instance_id = cls._normalize_instance_id(instance_id)
        state = await session.get(CommunicationRuntimeState, normalized_channel)
        if state is None or state.instance_id != normalized_instance_id:
            raise CommunicationRuntimeStateOwnershipLost(
                "Communication runtime state ownership was lost"
            )
        return cls._to_control(state)

    @classmethod
    async def read_active_owned_control(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        instance_id: str,
    ) -> CommunicationRuntimeControl:
        """Return owned control only while the operator permits full work."""

        control = await cls.read_owned_control(
            session,
            channel=channel,
            instance_id=instance_id,
        )
        if control.mode != CommunicationRuntimeMode.ALL:
            raise CommunicationRuntimeModeBlocked(control.mode)
        return control

    @classmethod
    async def record_status(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        instance_id: str,
        status: CommunicationRuntimeStatus | str,
        last_error_code: str | None = None,
        activity: bool = False,
    ) -> None:
        normalized_channel = cls._normalize_channel(channel)
        normalized_instance_id = cls._normalize_instance_id(instance_id)
        normalized_status = CommunicationRuntimeStatus(status)
        now = cls._now()
        values: dict[str, object] = {
            "status": normalized_status.value,
            "heartbeat_at": now,
            "last_error_code": cls._normalize_error_code(last_error_code),
            "updated_at": now,
        }
        if activity:
            values["last_activity_at"] = now
        result = await session.execute(
            update(CommunicationRuntimeState)
            .where(
                CommunicationRuntimeState.channel == normalized_channel,
                CommunicationRuntimeState.instance_id == normalized_instance_id,
            )
            .values(**values)
        )
        if result.rowcount != 1:
            raise CommunicationRuntimeStateOwnershipLost(
                "Communication runtime state ownership was lost"
            )

    @staticmethod
    def _to_control(state: CommunicationRuntimeState) -> CommunicationRuntimeControl:
        return CommunicationRuntimeControl(
            channel=state.channel,
            mode=CommunicationRuntimeMode(state.mode),
            status=CommunicationRuntimeStatus(state.status),
            instance_id=state.instance_id,
            heartbeat_at=state.heartbeat_at,
        )
