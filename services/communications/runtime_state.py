from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from models import CommunicationRuntimeState
from services.communications.canary_run_id import normalize_canary_run_id
from services.communications.processing_scope import CommunicationProcessingScope


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


class CommunicationRuntimeControlConflict(RuntimeError):
    def __init__(self, error_code: str) -> None:
        self.error_code = error_code
        super().__init__(error_code)


class CommunicationRuntimeModeBlocked(RuntimeError):
    def __init__(
        self,
        mode: CommunicationRuntimeMode,
        *,
        canary_run_id: str | None,
        control_revision: int,
    ) -> None:
        super().__init__("Communication runtime mode does not allow delivery work")
        self.mode = mode
        self.canary_run_id = canary_run_id
        self.control_revision = control_revision


@dataclass(frozen=True)
class CommunicationRuntimeControl:
    channel: str
    mode: CommunicationRuntimeMode
    canary_run_id: str | None
    control_revision: int
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
            canary_run_id=None,
            control_revision=0,
            status=CommunicationRuntimeStatus.STOPPED.value,
            control_updated_at=now,
            created_at=now,
            updated_at=now,
        )
        try:
            # The migration seeds the production row. The savepoint also makes
            # first-use initialization safe for isolated databases and tests:
            # concurrent callers race on the primary key without poisoning the
            # caller-owned outer transaction.
            async with session.begin_nested():
                session.add(state)
                await session.flush()
            return state
        except IntegrityError:
            concurrent_state = await session.get(
                CommunicationRuntimeState,
                normalized_channel,
                populate_existing=True,
            )
            if concurrent_state is None:  # pragma: no cover - defensive DB fence
                raise
            return concurrent_state

    @classmethod
    async def _lock_state(
        cls,
        session: AsyncSession,
        *,
        channel: str,
    ) -> CommunicationRuntimeState:
        normalized_channel = cls._normalize_channel(channel)
        state = await cls.ensure_state(session, channel=normalized_channel)
        if session.get_bind().dialect.name == "postgresql":
            state = await session.get(
                CommunicationRuntimeState,
                normalized_channel,
                populate_existing=True,
                with_for_update=True,
            )
            if state is None:  # pragma: no cover - protected by ensure_state
                raise RuntimeError("Communication runtime state disappeared")
        return state

    @staticmethod
    def _normalize_canary_scope(
        mode: CommunicationRuntimeMode,
        canary_run_id: str | None,
    ) -> str | None:
        if mode == CommunicationRuntimeMode.CANARY:
            if canary_run_id is None:
                raise ValueError("Canary runtime mode requires a run ID")
            return normalize_canary_run_id(canary_run_id)
        if canary_run_id is not None:
            raise ValueError("Only canary runtime mode accepts a run ID")
        return None

    @classmethod
    def _apply_control(
        cls,
        state: CommunicationRuntimeState,
        *,
        mode: CommunicationRuntimeMode,
        canary_run_id: str | None,
    ) -> None:
        now = cls._now()
        state.mode = mode.value
        state.canary_run_id = canary_run_id
        state.control_revision = int(state.control_revision) + 1
        state.control_updated_at = now
        state.updated_at = now

    @classmethod
    async def set_mode(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        mode: CommunicationRuntimeMode | str,
        canary_run_id: str | None = None,
    ) -> CommunicationRuntimeControl:
        normalized_mode = CommunicationRuntimeMode(mode)
        normalized_run_id = cls._normalize_canary_scope(
            normalized_mode,
            canary_run_id,
        )
        state = await cls._lock_state(session, channel=channel)
        current_mode = CommunicationRuntimeMode(state.mode)
        if current_mode == normalized_mode and state.canary_run_id == normalized_run_id:
            return cls._to_control(state)
        if (
            current_mode != CommunicationRuntimeMode.OFF
            and normalized_mode != CommunicationRuntimeMode.OFF
        ):
            raise CommunicationRuntimeControlConflict(
                "runtime_control_transition_requires_off"
            )
        cls._apply_control(
            state,
            mode=normalized_mode,
            canary_run_id=normalized_run_id,
        )
        await session.flush()
        return cls._to_control(state)

    @classmethod
    async def arm_canary_from_off(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        run_id: str,
    ) -> CommunicationRuntimeControl:
        normalized_run_id = normalize_canary_run_id(run_id)
        state = await cls._lock_state(session, channel=channel)
        if CommunicationRuntimeMode(state.mode) != CommunicationRuntimeMode.OFF:
            raise CommunicationRuntimeControlConflict("canary_runtime_not_off")
        cls._apply_control(
            state,
            mode=CommunicationRuntimeMode.CANARY,
            canary_run_id=normalized_run_id,
        )
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
        state = await cls._lock_state(session, channel=normalized_channel)
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
    async def read_control(
        cls,
        session: AsyncSession,
        *,
        channel: str,
    ) -> CommunicationRuntimeControl:
        state = await cls.ensure_state(session, channel=channel)
        return cls._to_control(state)

    @classmethod
    async def assert_owned_processing_scope(
        cls,
        session: AsyncSession,
        *,
        channel: str,
        instance_id: str,
        scope: CommunicationProcessingScope,
    ) -> CommunicationRuntimeControl:
        control = await cls.read_owned_control(
            session,
            channel=channel,
            instance_id=instance_id,
        )
        if not scope.matches_control(
            mode=control.mode.value,
            canary_run_id=control.canary_run_id,
            control_revision=control.control_revision,
        ):
            raise CommunicationRuntimeModeBlocked(
                control.mode,
                canary_run_id=control.canary_run_id,
                control_revision=control.control_revision,
            )
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
            canary_run_id=state.canary_run_id,
            control_revision=int(state.control_revision),
            status=CommunicationRuntimeStatus(state.status),
            instance_id=state.instance_id,
            heartbeat_at=state.heartbeat_at,
        )
